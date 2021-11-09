# -*- coding: utf-8 -*-

""" Main. """
import logging
import re
import os
import sys
import datetime
from functools import partial

from riana.project import ReadDirectory
from riana.peptides import ReadPercolator
from riana.spectra import Mzml

from riana import integrate, params, __version__

import tqdm
import pandas as pd

def runfit(args):
    pass

def runriana(args):
    """
    Improved process to integrate for isotope abundance analysis.
    Idea is to loop through the mzML only once - get all the peptides to be integrated first
    Find all the spectrum ID - m/z combinations to be integrated, then integrate them sequentially

    :param args: Arguments from command line
    :return:

    """

    # Get timestamp for out files
    now = datetime.datetime.now()

    # 2021-05-07 no longer creates subdirectory
    # directory_to_write = os.path.join(args.out, 'riana_' + now.strftime('%Y%m%d%H%M%S'))
    path_to_write = os.path.join(args.out)
    directory_to_write = os.path.dirname(path_to_write)
    os.makedirs(directory_to_write, exist_ok=True)

    main_log = logging.getLogger('riana')
    main_log.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    fh = logging.FileHandler(os.path.join(directory_to_write, 'riana.log')) # 'riana_' + now.strftime('%Y%m%d%H%M%S') + '.log'))
    fh.setLevel(logging.INFO)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)

    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    main_log.addHandler(fh)
    main_log.addHandler(ch)

    main_log.info(args)
    main_log.info(__version__)

    # Handle command line arguments
    unique_pep = args.unique

    # lysine_filter = args.lysine  # Does lysine peptides only (for Liverpool aa labeling data
    # try:
    #     lysine_filter = int(lysine_filter)
    #     if lysine_filter not in [1, 2, 3]:
    #         lysine_filter = 0
    #
    # except TypeError or ValueError:
    #     lysine_filter = 0

    #
    # Convert the to-do isotopomer list option into a list of integers
    #
    iso_to_do = []

    for char in args.iso.split(','):

        try:
            char = int(char)

            # Only doing down to mz + 15.
            if char <= 15:
                iso_to_do.append(int(char))

        except ValueError or TypeError:
            pass

    if not iso_to_do:
        sys.exit('Error: Invalid isotopomer list given.')

    iso_to_do = list(set(iso_to_do))
    iso_to_do.sort()

    #
    # Percolator q value cutoff for peptides and proteins
    #
    if args.qvalue:

        try:
            qcutoff = float(args.qvalue)

        except ValueError or TypeError:
            main_log.warning('Invalid Q value given - using default value.')
            qcutoff = float(1e-2)

    #
    # Retention time cutoff peptides and proteins
    #
    if args.rtime:

        try:
            rt_tolerance = float(args.rtime)

        except ValueError or TypeError:
            main_log.warning('Invalid retention time tolerance given - using default value.')
            rt_tolerance = float(1.0)
    else:
        rt_tolerance = float(1.0)

    #
    # MS1 mass tolerance for integration
    #
    if args.masstolerance:
        try:
            mass_tolerance = float(args.masstolerance) * 1e-6

        except ValueError or TypeError:
            main_log.warning('Invalid mass tolerance given - using default value.')
            mass_tolerance = float(100) * 1e-6
    else:
        mass_tolerance = float(100) * 1e-6

    #
    # Multi-threading
    #
    if args.thread:
        try:
            num_threads = max(os.cpu_count() * 4, int(args.thread))

        except ValueError or TypeError:
            print('Invalid thread count. Using default.')
            num_threads = os.cpu_count() * 4

    else:
        num_threads = os.cpu_count() * 4

    #
    # Inclusion lists
    #
    # if args.amrt:
    #     input_type = 'AMRT'  #"lipid"
    # else:
    #     input_type = 'Percolator'

    dir_loc = args.dir
    assert os.path.isdir(dir_loc), '[error] project directory not valid'

    # This is the directory that holds the entire project
    project = ReadDirectory(dir_loc)

    # Get the master peptide ID list
    # if input_type == 'Percolator':
    mzid = ReadPercolator(project=project,
                          directory_to_write=directory_to_write,
                          percolator_subdirectory=args.percolator)
    mzid.read_all_project_psms()

    # TODO: should remove mbr from the main integration function and move to a different script
    mzid.make_master_match_list(  # lysine_filter=0,
        peptide_q=qcutoff,
        unique_only=unique_pep,
        min_fraction=params.min_fraction_mbr)

    # Each subdirectory is a sample
    samples = project.samples
    # Create the grand total out file
    master_df = pd.DataFrame()

    for current_sample in tqdm.tqdm(samples, desc='Processing Sample', total=len(samples)):

        sample_loc = os.path.join(project.path, current_sample, 'mzml')

        mzid.get_current_sample_psms(current_sample=current_sample)
        mzid.get_current_sample_mzid_indices()

        #2021-11-04 account for mzml and mzML
        mzml_files = [f for f in os.listdir(sample_loc) if re.match('^.*.mz[Mm][Ll]', f)]

        # Sort the mzML files by names
        # Note this may create a problem if the OS Percolator runs on has natural sorting (xxxx_2 before xxxx_10)
        # But we will ignore for now
        mzml_files.sort()

        # Throw an error if there is no mzML file in the mzml directory
        assert len(mzml_files) != 0, '[error] no mzml files in the specified directory'
        # Check that the number of mzMLs in the mzML folder is the same as the maximum of the ID file's file_idx column.
        # Note this will break if the last fraction does not contain at least some ID, but we will ignore for now.
        assert len(mzml_files) == max(mzid.indices) + 1, '[error] number of mzml files not matching id list'

        # Create the sample master out file
        sample_master_df = pd.DataFrame()

        #
        # Read the mzml files and do integration
        #

        # For each file index (fraction), open the mzML file, and create a subset Percolator ID dataframe
        for idx in mzid.indices:

            # Verbosity 0 progress message
            main_log.info('Doing mzml: {0} ({1} of {2})'.format(
                mzml_files[idx],
                str(idx + 1),
                str(len(mzid.indices))))

            # Make a subset dataframe with the current file index (fraction) being considered
            mzid.get_current_fraction_psms(idx)
            mzid.filter_current_fraction_psms(  # lysine_filter=0,
                peptide_q=qcutoff,
                unique_only=unique_pep,
                use_soft_threshold=True,
                match_across_runs=False,  # args.mbr
            )

            try:
                mzml = Mzml(os.path.join(sample_loc, mzml_files[idx]))
            except OSError as e:
                sys.exit('[error] failed to load fraction mzml file. ' + str(e.errno))

            # #
            # # read the spectra into dictionary and also create MS1/MS2 indices
            # #
            mzml.parse_mzml()

            #
            # get peak intensity for each isotopomer in each spectrum ID in each peptide
            #
            # peaks.get_isotopes_from_amrt_multiwrapper(num_thread=num_thread)

            loop_ = range(len(mzid.curr_frac_filtered_id_df))

            integrate_one_partial = partial(integrate.integrate_one,
                                            id_=mzid.curr_frac_filtered_id_df.copy(),
                                            iso_to_do=iso_to_do,
                                            mzml=mzml,
                                            rt_tolerance=rt_tolerance,
                                            mass_tolerance=mass_tolerance,
                                            deuterium_mass_defect=args.deuterium,
                                            )

            # Single threaded loop
            # '''
            # results = []
            # for i in loop_:
            #     print(i)
            #     results += integrate_one_partial(i)
            # '''

            # For parellization, use concurrent.futures instead of multiprocessing for higher speed
            # '''
            from concurrent import futures
            with futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
                result = list(tqdm.tqdm(ex.map(integrate_one_partial, loop_),
                                        total=max(loop_),
                                        desc='Integrating Peaks in Current Sample'))
            # '''

            #
            # Convert the output_table into a data frame
            #
            df_columns = ['ID', 'pep_id'] + ['m' + str(iso) for iso in iso_to_do]
            result_df = pd.DataFrame(result, columns=df_columns)
            id_result_df = pd.merge(mzid.curr_frac_filtered_id_df, result_df, on='pep_id', how='left')
            id_result_df['file'] = mzml_files[idx]

            # Bind rows of the current result to the sample master
            if len(sample_master_df.index) == 0:
                sample_master_df = id_result_df
            else:
                sample_master_df = sample_master_df.append(id_result_df, ignore_index=True)

        # 2021-05-07 No longer creates subfolder
        # Create subdirectory if not exists
        # os.makedirs(os.path.join(directory_to_write, current_sample), exist_ok=True)
        # save_path = os.path.join(directory_to_write, current_sample, mzml_files[idx] + '_riana.txt')

        save_path = os.path.join(directory_to_write, current_sample + '_riana.txt')
        sample_master_df.to_csv(save_path, sep='\t')

        # Make the soft-threshold data frame. These are the peptides that are ID'ed at 10 times the q-value
        # as the cut-off in this fraction up to q < 0.1, but has q >= q-value cutoff, and furthermore has been
        # consistently identified in the other samples at the same fraction (median fraction) at the q-value cutoff

        # Bind rows of the current sample master to the total (all time point output) master
        if len(master_df.index) == 0:
            master_df = sample_master_df
        else:
            master_df = master_df.append(sample_master_df, ignore_index=True)

    # Write out the total time point output
    master_df.to_csv(path_to_write, sep='\t')

    return sys.exit(os.EX_OK)


#
# Code for running main with parsed arguments from command line
#
def main():
    import argparse

    parser = argparse.ArgumentParser(description='Riana integrates the relative abundance of'
                                                 'isotopomers')


    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s {version}'.format(version=__version__))

    # Sub-commands
    subparsers = parser.add_subparsers(help='Type riana function -h for individual help messages',
                                       title='Functions',
                                       description='Riana has the following sub-commands:',
                                       )
    parser_integrate = subparsers.add_parser('integrate',
                                             aliases=['int'],
                                             help='Integrates isotopomer abundance over retention time')
    parser_fit = subparsers.add_parser('fit',
                                       help='Fit to kinetic models. Note implemented yet.')

    # Arguments for integrate subcommand
    parser_integrate.add_argument('dir',
                                  help='path to folders containing the mzml and search files (see documentation)')

    parser_integrate.add_argument('-i', '--iso',
                                  help='isotopes to do, separated by commas, e.g., 0,1,2,3,4,5 [default: 0,6]',
                                  default='0,6')

    parser_integrate.add_argument('-d', '--deuterium',
                                  action='store_true',
                                  help='experimental feature: use mass defect for deuterium.')

    parser_integrate.add_argument('-u', '--unique',
                                  action='store_true',
                                  help='integrate unique peptides only')

    parser_integrate.add_argument('-t', '--thread', help='number of threads for concurrency; leave as 0 for auto (default = 0)',
                        type=int,
                        default=0)

    parser_integrate.add_argument('-o', '--out', help='path to the output directory [default: riana]',
                        default='riana')

    # parser_integrate.add_argument('--amrt', action='store_true', help='integrate an inclusion list of AM-RTs',
    #                     default=False)

    # parser_integrate.add_argument('-k', '--lysine',
    #                     help='lysine mode, 0=No filter, 1=1 K, 2=1 or more K, 3=KK only [default = 0]',
    #                     type=int,
    #                     choices=[0, 1, 2, 3],
    #                     default=0)

    # parser_integrate.add_argument('-b', '--mbr', action='store_true', help='attempt to match between runs',
    #                    default=False)

    parser_integrate.add_argument('-q', '--qvalue',
                                  help='integrate only peptides with q value below this threshold[default: 1e-2]',
                                  type=float,
                                  default=1e-2)

    parser_integrate.add_argument('-r', '--rtime',
                                  help='retention time (in minutes, both directions) tolerance for integration',
                                  type=float,
                                  default=1.0)

    parser_integrate.add_argument('-m', '--masstolerance',
                                  help='mass tolerance in ppm for integration [default 50 ppm]',
                                  type=float,
                                  default=50)

    parser_integrate.add_argument('-p', '--percolator',
                                  help='subdirectory name of percolator folder (default = percolator)',
                                  type=str,
                                  default='percolator')

    parser_integrate.set_defaults(func=runriana)

    # Arguments for fit subcommand
    parser_fit.set_defaults(func=runfit)

    # Print help message if no arguments are given
    import sys
    if len(sys.argv[1:]) == 0:
        parser.print_help()
        parser.exit()

    # gc.enable()
    # gc.set_debug(gc.DEBUG_LEAK)

    # Parse all the arguments
    args = parser.parse_args()

    # Run the function in the argument
    args.func(args)
