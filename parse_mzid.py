"""

Python mzid Parser v.0.1.0. Build Date : : :.
Written by Edward Lau (edward.lau@me.com)

Classes that concern parsing mzIdentML files and creating summary tables


"""

from time import time
from xml.dom import minidom
import pandas as pd
import os.path
import sys
import re
import numpy as np

class Mzid(object):
    """
    This class holds the loaded mzIdentml object and extracts peptides and protein labels.
    Goal is to get dataframe where identified peptide sequence/z combos are linked to their m/z, protein and spectrum ID
    To do so, first pull 5 tables from the mzID file: 1.PSM, 2.Peptide, 3.ProteinGroup, 4.PeptideEvidence, 5.DBSequence

    1. PSM contains spectrum_ID, mz, z passThreshold; references to Peptide and PeptideEvidence through Pep_ref & PE_ref
    2. Peptide contains the actual amino acid sequence
    3. ProteinGroup contains passThreshold, references to DBSequence and PeptideEvidence through DBS_ref and PE_Ref
    4. PeptideEvidence contains isDecoy, references to Peptide and DBSequence through Pep_ref and DBS_ref
    5. DBSequence contains the Uniprot accession number

    From these five tables, output a peptide-centric summary, and a protein-centric summary
    Peptide-centric Summary combines PSM and Peptide, contains Sequence, mz, z, spectrumID
    Protein-centric Summary reads all 5 tables, should contain Uniprot in addition to peptide-centric summary

    """

    def __init__(self, path):
        """
        :param path: path of the mzid file to be loaded, e.g., "~/Desktop/example.mzid"


        """
        self.path = os.path.join(path)
        self.root = self.parse_file()

        self.psm_df = self.read_psm()
        self.peptide_df = self.read_peptide()
        self.protein_df = self.read_protein()
        self.pe_df = self.read_pe()
        self.dbs_df = self.read_dbs()

        self.pep_summary_df = pd.DataFrame()
        self.pro_summary_df = pd.DataFrame()

        self.filtered_protein_df = pd.DataFrame()
        self.filtered_pep_summary_df = pd.DataFrame()

    def parse_file(self):
        """
        Get the mzid file xml root
        NB: Move time tracker to main loop when made into object oriented.

        :return: True
        """

        print('Reading mzID file as document object model...')
        t1 = time()
        xmldoc = minidom.parse(self.path).childNodes[0]
        t2 = time()
        print('Done. Processing time: ' + str(round(t2 - t1, 2)) + ' seconds.')

        # Check if this is mzML 1.1 or above
        if xmldoc.attributes['version'].value < '1.1.0':
            sys.exit('mzML version is not 1.1 or above.')

        else:
            return xmldoc

    def read_psm(self):
        """
        Table #1 : All PSM Identified

        :return: psm_df     - A dataframe containing all peptide spectrum matches
        """

        allPsmList = []

        # Traverse to DataCollection > SpectrumIdentificationList
        # Note we jump past AnalysisData, assuming there is only one such section
        DataCollection = self.root.getElementsByTagName('DataCollection')[0]
        SpectrumIdentificationList = DataCollection.getElementsByTagName('SpectrumIdentificationList')[0]

        # How many SpectrumIdentificationResult entries are in each SpectrumIdentificationList ?
        # Traverse down to SpectrumIdentificationResult. Each SIR is linked to one spectrum ID but possibly multiple SII
        # Each SII is a PSM.
        SpectrumIdentificationResult = SpectrumIdentificationList.getElementsByTagName('SpectrumIdentificationResult')

        for i in range(0, len(SpectrumIdentificationResult)):

            # Print progress every 1000 records
            if i % 1000 == 0:
                print('Processing ' + str(i) + ' of ' + str(len(SpectrumIdentificationResult)) + ' records (PSM).')

            sir_id = SpectrumIdentificationResult[i].attributes['id'].value
            spectrum_id = SpectrumIdentificationResult[i].attributes['spectrumID'].value.split('-')[0]

            # Traverse down to the SII entries inside each SIR
            SpectrumIdentificationItem = SpectrumIdentificationResult[i].getElementsByTagName(
                'SpectrumIdentificationItem')

            for j in range(0, len(SpectrumIdentificationItem)):

                psmList = []

                sii_id = SpectrumIdentificationItem[j].attributes['id'].value
                z = SpectrumIdentificationItem[j].attributes['chargeState'].value
                mz = SpectrumIdentificationItem[j].attributes['experimentalMassToCharge'].value
                calc_mz = SpectrumIdentificationItem[j].attributes['calculatedMassToCharge'].value
                pep_id = SpectrumIdentificationItem[j].attributes['peptide_ref'].value
                pass_threshold = SpectrumIdentificationItem[j].attributes['passThreshold'].value

                # Get the Peptide Evidence Ref (need this to link to other tables later)
                PeptideEvidenceRef = SpectrumIdentificationItem[j].getElementsByTagName('PeptideEvidenceRef')[0]


                pe_id = PeptideEvidenceRef.attributes['peptideEvidence_ref'].value

                # Put SIR ID, spectrum_ID, SII ID, z, m/z, theoretical m/z, Peptide ID, passThreshold, PE ID into list
                psmList.extend([sir_id, spectrum_id, sii_id, z, mz, calc_mz, pep_id, pass_threshold, pe_id])

                # Get the list of all cvParams from each SII (e.g.,percolator scores)
                cvParams = SpectrumIdentificationItem[j].getElementsByTagName('cvParam')

                for cvParam in cvParams:
                    acc = cvParam.attributes['accession'].value
                    name = cvParam.attributes['name'].value
                    value = cvParam.attributes['value'].value
                    cvParamList = [acc, name, value]
                    psmList.append(cvParamList)
                    # peptideList.append(acc)
                    # peptideList.append(name)
                    # peptideList.append(value)

                    # Add each PSM's psmList of info into the list of lists
                    allPsmList.append(psmList)



        # Convert into pandas dataframe
        psm_df = pd.DataFrame(allPsmList)
        psm_df.to_csv("all_psms.txt",sep='\t')
        print(psm_df)
        #
        # Rename the columns in the PSM table
        #

        # Get column names
        colnames = psm_df.columns.tolist()

        # Create a dictionary that map old names to new names
        # The first three columns are ID, Sequence
        newcol = {0: 'sir_id',
                  1: 'spectrum_id',
                  2: 'sii_id',
                  3: 'z',
                  4: 'mz',
                  5: 'calc_mz',
                  6: 'pep_id',
                  7: 'pep_pass_threshold',
                  8: 'pe_id',
                  }

        # Getting the name of the cvParam from the first row of the ith column of the dataframe
        for i in range(9, len(colnames)):
            newcol[i] = re.sub(' |:', '_', psm_df[i][0][1])
            temp = []
            for acc, name, value in psm_df[i]:
                temp.append(value)
            psm_df[i] = temp

        psm_df.rename(columns=newcol, inplace=True)

        return psm_df

    def read_peptide(self):
        """
        Table # 2: Peptide Sequences Identified

        Get the values inside Peptide. This is needed because the SII (PSM) refers only to Peptide_ref
        Peptide_ref needs to be looked up to get the sequence

        :return:
        """

        ## Traverse down to Sequence Collection > Peptide
        SequenceCollection = self.root.getElementsByTagName('SequenceCollection')[0]
        Peptide = SequenceCollection.getElementsByTagName('Peptide')

        allPeptideList = []

        for i in range(0, len(Peptide)):

            peptideList = []

            # Print progress every 1000 records
            if i % 1000 == 0:
                print('Processing ' + str(i) + ' of ' + str(len(Peptide)) + ' records (Peptides).')

            pep_id = Peptide[i].attributes['id'].value

            PeptideSequence = Peptide[i].getElementsByTagName('PeptideSequence')[0]
            seq = PeptideSequence.childNodes[0].nodeValue

            # Put Peptide ID and peptide sequence into peptideList
            peptideList.extend([pep_id, seq])

            # Get the cvParams from each Peptide (percolator scores)
            cvParams = Peptide[i].getElementsByTagName('cvParam')

            for cvParam in cvParams:
                acc = cvParam.attributes['accession'].value
                name = cvParam.attributes['name'].value
                value = cvParam.attributes['value'].value
                cvParamList = [acc, name, value]
                peptideList.append(cvParamList)

            allPeptideList.append(peptideList)

        peptide_df = pd.DataFrame(allPeptideList)

        #
        # Rename the columns in the peptide table
        #

        # Get column names
        colnames = peptide_df.columns.tolist()

        # Create a dictionary that map old names to new names
        # The first three columns are ID, Sequence
        newcol = {0: 'pep_id',
                  1: 'seq',
                  }

        # Getting the name of the cvParam from the first row of the ith column of the dataframe
        for i in range(2, len(colnames)):
            newcol[i] = re.sub(' |:', '_', peptide_df[i][0][1])
            temp =[]
            for acc, name, value in peptide_df[i]:
                temp.append(value)
            peptide_df[i] = temp

        peptide_df.rename(columns=newcol, inplace=True)

        return peptide_df

    def read_protein(self):
        """
         Retrieve ProteinAmbiguityGroup for all identified proteins from the mzIdentML file.

        :return:
        """

        # Traverse to DataCollection > ProteinDetectionList
        DataCollection = self.root.getElementsByTagName('DataCollection')[0]
        ProteinDetectionList = DataCollection.getElementsByTagName('ProteinDetectionList')

        # Traverse down to each ProteinAmbiguityGroup from each ProteinDetectionList - There are multiple PAG per PDL
        ProteinAmbiguityGroup = ProteinDetectionList[0].getElementsByTagName('ProteinAmbiguityGroup')

        allProteinList = []

        for i in range(0, len(ProteinAmbiguityGroup)):

            # Print progress every 1000 records
            if i % 1000 == 0:
                print('Processing ' + str(i) + ' of ' + str(len(ProteinAmbiguityGroup)) + ' records (Proteins).')

            pag_id = ProteinAmbiguityGroup[i].attributes['id'].value

            # Traverse down to each Protein Detection Hypothesis from each Protein Ambiguity Group.
            # There may be >1 PDH per PAG in some files, but in the test files I have done.
            # (From Comet and Tide, but only single fraction) there is only 1 PDH per PAG.
            # It is possible that for multi-fraction runs there can be multiple PDH per PAG.
            ProteinDetectionHypothesis = ProteinAmbiguityGroup[i].getElementsByTagName('ProteinDetectionHypothesis')[0]

            # Grab the ProteinDetectionHypothesis ID, DBSequence Reference, and Threshold flag
            pdh_id = ProteinDetectionHypothesis.attributes['id'].value
            dbs_id = ProteinDetectionHypothesis.attributes['dBSequence_ref'].value
            pass_threshold = ProteinDetectionHypothesis.attributes['passThreshold'].value


            # Get the cvParams from each ProteinDetectionHypothesis (e.g., percolator scores)
            cvParams = ProteinDetectionHypothesis.getElementsByTagName('cvParam')

            # Traverse down to each Peptide Hypothesis from each Protein Detection Hypothesis

            PeptideHypothesis = ProteinDetectionHypothesis.getElementsByTagName('PeptideHypothesis')

            for j in range(0, len(PeptideHypothesis)):
                pe_id = PeptideHypothesis[j].attributes['peptideEvidence_ref'].value

                # Traverse down to each SII Ref from each PeptideHypothesis
                SpectrumIdentificationItemRef = PeptideHypothesis[j].getElementsByTagName('SpectrumIdentificationItemRef')

                for k in range(0, len(SpectrumIdentificationItemRef)):
                    sii_id = SpectrumIdentificationItemRef[k].attributes['spectrumIdentificationItem_ref'].value

                    # Put pag_id, pdh_id, dbs_ref, pass_threshold, pe_ref, and sii_ref into the proteinList of a particular PAG
                    proteinList = []
                    proteinList.extend([pag_id, pdh_id, dbs_id, pass_threshold, pe_id, sii_id])

                    for cvParam in cvParams:
                        acc = cvParam.attributes['accession'].value
                        name = cvParam.attributes['name'].value
                        value = cvParam.attributes['value'].value
                        cvParamList = [acc, name, value]
                        proteinList.append(cvParamList)

                    allProteinList.append(proteinList)

        protein_df = pd.DataFrame(allProteinList)

        #
        # Rename the columns in the peptide table
        #

        # Get column names
        colnames = protein_df.columns.tolist()

        # Create a dictionary that map old names to new names
        # The first three columns are ID, Sequence
        newcol = {0: 'pag_id',
                  1: 'pdh_id',
                  2: 'dbs_id',
                  3: 'prot_pass_threshold',
                  4: 'pe_id',
                  5: 'sii_id',
                  }

        # Getting the name of the cvParam from the first row of the ith column of the dataframe
        for i in range(6, len(colnames)):
            newcol[i] = re.sub(' |:', '_', protein_df[i][0][1])
            temp = []
            for acc, name, value in protein_df[i]:
                temp.append(value)
            protein_df[i] = temp


        protein_df.rename(columns=newcol, inplace=True)

        return protein_df


    def read_pe(self):
        # Table #4. PeptideEvidence
        # This is read to see whether sequence isDecoy, and to link each PAG's PeptideHypothesis to a Peptide and a DBSequence


        ## Traverse down to Sequence Collection > DBSequence
        SequenceCollection = self.root.getElementsByTagName('SequenceCollection')[0]
        PeptideEvidence = SequenceCollection.getElementsByTagName('PeptideEvidence')

        allPEList = []

        for i in range(0, len(PeptideEvidence)):

            peList = []

            # Print progress every 1000 records
            if i % 1000 == 0:
                print('Processing ' + str(i) + ' of ' + str(len(PeptideEvidence)) + ' records (PeptideEvidence).')

            pe_id = PeptideEvidence[i].attributes['id'].value
            pep_id = PeptideEvidence[i].attributes['peptide_ref'].value
            dbs_id = PeptideEvidence[i].attributes['dBSequence_ref'].value
            start = PeptideEvidence[i].attributes['start'].value
            end = PeptideEvidence[i].attributes['end'].value
            is_decoy = PeptideEvidence[i].attributes['isDecoy'].value

            # Add PeptideEvidence ID and reference to Peptide, reference DBSequence, and isDecoy flag to peList
            peList.extend([pe_id, pep_id, dbs_id, start, end, is_decoy])

            allPEList.append(peList)

        pe_df = pd.DataFrame(allPEList)

        #
        # Rename the columns in the peptide table
        #

        # Get column names
        colnames = pe_df.columns.tolist()

        # Create a dictionary that map old names to new names
        # The first three columns are ID, Sequence
        newcol = {0: 'pe_id',
                  1: 'pep_id',
                  2: 'dbs_id',
                  3: 'start',
                  4: 'end',
                  5: 'is_decoy',
                  }

        pe_df.rename(columns=newcol, inplace=True)

        return pe_df


    def read_dbs(self):
        #
        # Table #5: DBSequences
        # This is read to get the Uniprot accession of each identified peptide
        #


        ## Traverse down to Sequence Collection > DBSequence
        SequenceCollection = self.root.getElementsByTagName('SequenceCollection')[0]
        DBSequence = SequenceCollection.getElementsByTagName('DBSequence')

        allDBSList = []

        for i in range(0, len(DBSequence)):

            dbsList = []

            # Print progress every 1000 records
            if i % 1000 == 0:
                print('Processing ' + str(i) + ' of ' + str(len(DBSequence)) + ' records (DatabaseSequences).')

            dbs_id = DBSequence[i].attributes['id'].value
            length = DBSequence[i].attributes['length'].value
            acc = DBSequence[i].attributes['accession'].value

            # Add DBSequence ID, sequence length, and Uniprot accession to the dbsList
            dbsList.extend([dbs_id, length, acc])

            allDBSList.append(dbsList)

        dbs_df = pd.DataFrame(allDBSList)

        #
        # Rename the columns in the peptide table
        #

        # Get column names
        colnames = dbs_df.columns.tolist()

        # Create a dictionary that map old names to new names
        # The first three columns are ID, Sequence
        newcol = {0: 'dbs_id',
                  1: 'length',
                  2: 'uniprot',
                  }

        dbs_df.rename(columns=newcol, inplace=True)

        return dbs_df

    def make_peptide_summary(self):
        """
        Take the five Mzid data frames, and return a flat table after filtering for Q values

        It first combines PSM and Peptide into a peptide-centric summary.

        :return: True
        """

        # From these five tables, output a peptide-centric summary, and a protein-centric summary
        # Peptide-centric Summary combines PSM and Peptide, contains Sequence, mz, z, spectrumID


        # Alternatively, assuming the percolator scores are already sorted
        self.psm_df = self.psm_df.groupby('pep_id', sort=False).first().reset_index()

        self.pep_summary_df = pd.merge(self.peptide_df, self.psm_df[self.psm_df.columns[0:8]], how='left')

        return True

    def filter_peptide_summary(self, lysine_filter=0, protein_q=1e-2, peptide_q=1e-2, unique_only=False):
        """
        The peptide-centric summary is then fitered by:
        - peptides that belong to any protein identified at a protein Q value
        - peptides below a certain peptide Q value
        - peptides containing certain number of lysines

        :param lysine_filter: Lysine filter from command line argument
        :param protein_q: Protein-level Q value from command line argument
        :param peptide_q: Peptide-level Q value from command line argument
        :param unique_only: Only doing unique peptides
        :return: True
        """

        #
        # Filter peptides by Protein Q value
        #
        try:
            self.filtered_protein_df = self.protein_df.loc[lambda x: x.percolator_Q_value.astype(float) < protein_q, :]
            #self.filtered_protein_df = self.filtered_protein_df.reset_index()
        except:
            print('Filtering protein failed.')
            self.filtered_protein_df = self.protein_df.loc


        #
        # Filter peptides by peptide-level Q-value filter
        #
        try:
            self.pep_summary_df = self.pep_summary_df.loc[lambda x: x.percolator_Q_value.astype(float) < peptide_q, :]
            self.pep_summary_df = self.pep_summary_df.reset_index(drop=True)

        except:
            pass

        #
        # Filter peptides by optional lysine filter
        #

        # If the lysine filter is on and the peptide has no or more than one lysine, skup
        if lysine_filter == 1:
            try:
                self.pep_summary_df = self.pep_summary_df.loc[lambda x: x.seq.apply(lambda y: y.count('K')) == 1, :]
                self.pep_summary_df = self.pep_summary_df.reset_index(drop=True)

            except:
                pass

        if lysine_filter == 2:
            try:
                self.pep_summary_df = self.pep_summary_df.loc[lambda x: x.seq.apply(lambda y: y.count('K')) > 0, :]
                self.pep_summary_df = self.pep_summary_df.reset_index(drop=True)

            except:
               pass

        self.filtered_pep_summary_df = pd.merge(self.pep_summary_df,
                                                self.filtered_protein_df[self.filtered_protein_df.columns[[0,5]]],
                                                how='inner')


        #
        # Get the protein Uniprot accession via PE and then via DBS
        #
        self.filtered_pep_summary_df = pd.merge(self.filtered_pep_summary_df, self.pe_df, how='left')
        self.filtered_pep_summary_df = pd.merge(self.filtered_pep_summary_df, self.dbs_df, how='left')
        self.filtered_pep_summary_df = self.filtered_pep_summary_df.reset_index(drop=True)

        # Get only the peptides associated with one and only one proteins
        if unique_only:

            try:
                self.filtered_pep_summary_df = self.filtered_pep_summary_df.groupby('seq').filter(lambda x: (len(set(x['uniprot'])) == 1))
                self.filtered_pep_summary_df = self.filtered_pep_summary_df.reset_index(drop=True)

            except:
                pass

        self.filtered_pep_summary_df = self.filtered_pep_summary_df.reset_index(drop=True)

        return True

#
#   For doctest
#
if __name__ == '__main__':
    import doctest
    doctest.testmod()