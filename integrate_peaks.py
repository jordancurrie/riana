"""

Integrate Peaks v.0.1.0. Build Date : : :.
Written by Edward Lau (edward.lau@me.com) 2016-2017


"""

import pandas as pd
import scipy.integrate
import tqdm
from multiprocessing import Pool, cpu_count

class Peaks(object):
    def __init__(self, msdata, rt_idx, mslvl_idx):
        """
        This class uses the parsed peaks from pymzml for peak recognition and counting

        :param msdata: The dictionary of spectrum ID vs. mz/I array from parse Mzml
        :param rt_idx: The retention time index dictionary from parse Mzml
        :param mslvl_idx: The spectrum MS level dictionary from parse Mzml
        """

        self.msdata = msdata
        self.rt_idx = rt_idx
        self.mslvl_idx = mslvl_idx
        self.id = pd.DataFrame()
        self.iso_to_do = []
        self.rt_tolerance = 30
        self.mass_tolerance = 100e-6
        self.njobs = 10
        self.intensity_over_time = []
        self.isotope_intensities = []

    def set_iso_to_do(self, iso_to_do):
        """
        Setter for isotope
        :param iso_to_do:
        :return:
        """

        self.iso_to_do = iso_to_do

    def set_rt_tolerance(self, rt_tolerance):
        """
        Setter for rt_tolerance

        :param rt_tolerance:
        :return:
        """

        self.rt_tolerance = rt_tolerance

    def set_mass_tolerance(self, mass_tolerance):
        """
        Setter for mass tolerance
        :param iso_to_do:
        :return:
        """

        self.mass_tolerance = mass_tolerance

    def associate_id(self, id_df):
        """
        Associate the mzid peptide identification file to this peak list

        :param id_df: Fraction-specific ID list from mzid or Percolator
        :return:
        """

        self.id = id_df

    def get_isotopes_from_amrt_multiwrapper(self, num_thread=1):

        """
        Multi-threaded wrapper to get the isotopomers from peptide accurate mass and retention time of all qualifying
        peptides at the same time. The chunk size of multithreading is set to 50 at the moment.

        :param num_thread: Number of threads (default to 1)
        :return:
        """

        assert num_thread >= cpu_count()-1, "Number of threads exceeded CPU count"

        with Pool(processes=num_thread) as p:
            result = list(tqdm.tqdm(p.imap(self.get_isotopes_from_amrt_wrapper,
                                           range(len(self.id)), chunksize=50), total=len(self.id)))

        return result


    def get_isotopes_from_amrt_wrapper(self, index):
        """
        Wrapper for the get_isotope_from_scan_id() function below

        :param index: int The row number of the peptide ID table passed from the wrapper.
        :return: list [index, pep_id, m0, m1, m2, ...]
        """
        self.intensity_over_time = self.get_isotopes_from_amrt(peptide_am=float(self.id.loc[index, 'peptide mass']), # spectrum precursor m/z'
                                        peptide_scan=int(self.id.loc[index, 'scan']),
                                        z=float(self.id.loc[index, 'charge'])
                                                                 )

        result = [index] + [(self.id.loc[index, 'pep_id'])] + self.integrate_isotope_intensity()

        return result


    def get_isotopes_from_amrt(self, peptide_am, peptide_scan, z):
        """
        Given peptide accurate mass and retention time and charge, find all the isotopic peaks intensity at each
        scan within the retention time window

        :param peptide_am: float Accurate peptide mass
        :param peptide_scan: int Scan number
        :param z: int Peptide charge
        :return: List of intensity over time
        """

        # Get retention time from scan number
        peptide_rt = self.rt_idx.get(peptide_scan)

        # Calculate precursor mass from peptide monoisotopic mass
        peptide_prec = (peptide_am + (z * 1.007825)) / z


        intensity_over_time = []

        # Choose the scan numbers from the index; one-line list comprehension?
        nearby_scans = [[i, rt] for i, rt in self.rt_idx.items()
                        if abs(rt - peptide_rt) <= self.rt_tolerance and self.mslvl_idx[i] == 1]

        # Loop through each spectrum, check if it is an MS1 spectrum, check if it is within 1 minute of retention time
        for nearbyScan_id, nearbyScan_rt in nearby_scans:
            # Get the spectrum based on the spectrum number

            for iso in self.iso_to_do:

                peptide_prec_isotopomer_am = peptide_prec + (iso * 1.007825 / z)
                upper = peptide_prec_isotopomer_am + (peptide_prec_isotopomer_am * (self.mass_tolerance/2))
                lower = peptide_prec_isotopomer_am - (peptide_prec_isotopomer_am * (self.mass_tolerance/2))

                matching_int = sum([I for mz_value, I in self.msdata.get(nearbyScan_id) if upper > mz_value > lower])

                intensity_over_time.append([nearbyScan_rt, iso, matching_int, peptide_prec_isotopomer_am])

        return intensity_over_time

    def integrate_isotope_intensity(self):
        """
        Given a list of isotopomer intensity over time, give the integrated intensity of each isotopomer

        :return: Integrated intensity of each isotopomer
        """
        # Integrate the individual isotopomers
        iso_intensity = []

        for j in self.iso_to_do:

            isotopomer_profile = [[rt, I] for rt, iso, I, mz_value in self.intensity_over_time if iso == j]

            # If there is no isotopomer profile, set area to 0
            if isotopomer_profile:
                iso_df = pd.DataFrame(isotopomer_profile)
                iso_area = scipy.integrate.trapz(iso_df[1], iso_df[0])
                # Remove all negative areas
                iso_area = max(iso_area, 0)

            else:
                iso_area = 0

            iso_intensity.append(iso_area)

        return iso_intensity
