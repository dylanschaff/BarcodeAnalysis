#Script to generate barcode targeting probes with HCR adapters. 

import os, glob 
import itertools
import numpy as np
import pandas as pd
import Levenshtein
import regex as re
from argparse import ArgumentParser

#Command line parser
parser = ArgumentParser()
parser.add_argument("path", help = "Specify the path to the experiment directory containing subdirectories with the extracted barcodes.", type = str)
parser.add_argument("sample", help = "Specify the name of the sample", type = str)
parser.add_argument("-n", "--number", help = "Option to specify a minimum number of probe needed to keep the barcode target. Default value is 4", default = 4, type = int)
parser.add_argument("-I", "--initiators", help = "Option to specify the split initiators to append to the probes. Default will be to use B1 initiators", nargs = 2, default = ['GAGGAGGGCAGCAAACGGAA', 'TAGAAGAGTCTTCCTTTACG'])
parser.add_argument("-c", "--checkSequence", help = "Option to specify a mask sequence (fasta format). Will output the minimum number of mismatches to the sequence for each probe. Input single fasta formatted sequence", type = str)
parser.add_argument("-u", "--checkUnusedSample", help = "Option to specify a table of barcode to check each probe against. Please specify a rank cutoff using option --rank", type = str)
parser.add_argument("-r", "--rank", help = "If --checkUnusedSample is used, please specify the rank used to select barcodes for targetting. Default is 200", default = 200, type = int)
parser.add_argument("-s", "--sampleUnused", help = "Option to specify the number of unused barcode to screen for matches to designed probes. Default is 1000", default =1000, type = int)
parser.add_argument("-f", "--fullLengthSequence", help = "If specified output table of the full length probes with designed barcodes", action='store_true')
parser.add_argument("-o", "--outFileName", help = "Option to specify the prefix of the output file. Default will be to use the input sample name", type = str)
args = parser.parse_args()

def readHCROligos(filename):
	"""Function to read in oligos file output by findProbesHD and split
	desgined 42mer into 2 20mers with a 2nt gap in between. 
	"""
	probeList = []
	with open(filename, 'r') as probeFile:
		for line in probeFile.readlines():
			line = line.strip('\n').split('\t')
			probeList.extend([line[4][0:20], line[4][22:42]])
	return probeList

def calcGC(sequence):
    count = sequence.lower().count('g') + sequence.lower().count('c')
    return float(count)/len(sequence)

def reverse_complement(sequence):
    complement = {'a':'t', 't': 'a', 'g':'c', 'c':'g', 'n':'n'}
    reverseComplement = "".join([complement[base] for base in str(sequence)[::-1].lower()])
    return reverseComplement     

def getMinHamming(probeList, sequenceList):
    minHammingList = [min([Levenshtein.hamming(i, reverse_complement(j)) for j in sequenceList]) for i in probeList]
    return minHammingList

def addSplitInitiators(probeList, I1, I2):
    """"Function to append split initiators (I1 and I2) to probes in probeList. 
    Note that I1 will be appended 5prime to every odd probe (1, 3, 5 ...) 
    and I2 will be appended 3prime to every even probe (0, 2, 4...)
    """
    newProbes = []
    for i, probe in enumerate(probeList):
        if i%2 == 1:
            newProbes.append("".join([I1, probe]))
        elif i%2 == 0:
            newProbes.append("".join([probe, I2]))
    return newProbes

def checkDuplicates(probeSet, allProbes):
	"""Function to check if probes in probeset
	occur once or more times in allProbes"""
	dupList = []
	for i in probeSet:
		if allProbes.count(i) == 1:
			dupList.append("No")
		elif allProbes.count(i) > 1:
			dupList.append("Yes")
	return dupList

oligoPath = os.path.join(args.path, 'barcodeDesign', args.sample, 'probeDesignHCR/')
oligoFiles = glob.glob(oligoPath + "*_oligos.txt")

probeDict = {}
for file in oligoFiles:
    probeDict[re.search(r'barcode\d+', file).group()] = readHCROligos(file)

#Remove barcodes with too few probes:
badBarcodes = {}
for barcode in probeDict.keys():
    if len(probeDict[barcode]) < args.number:
        badBarcodes[barcode] = probeDict.pop(barcode)

#Check if probe is duplicated
allProbes = [probe for sublist in probeDict.values() for probe in sublist]

for barcode, probes in probeDict.iteritems():
    probeDict[barcode].extend(checkDuplicates(probes[0:4], allProbes))

#Calc GC% for each probe
for barcode, probes in probeDict.iteritems():
    probeDict[barcode].extend([calcGC(i) for i in probes[0:4]])

header = ["Name", "Sequence", "Duplicated", "GC"]

if args.checkSequence is not None:
	with open(args.checkSequence, 'r') as checkFile:
		head = checkFile.readline().strip('\n')
		seqToCheck = checkFile.readline().strip('\n')
	seqToCheck = [seqToCheck[i:i+20] for i in xrange(0, len(seqToCheck)-20 + 1)]
	for barcode, probes in probeDict.iteritems():
		probeDict[barcode].extend(getMinHamming(probes[0:4], seqToCheck))
	header.append("minMatchCheckedSequence")

if args.checkUnusedSample is not None:
	sample_df = pd.read_csv(str(args.checkUnusedSample), names=["barcode", "reads"], sep = '\t')
	sample_df = sample_df.sort_values(by = 'reads', ascending=False).iloc[args.rank:,:]
	sample_barcodes = sample_df.loc[sample_df['reads'] >= 10].sample(n = args.sampleUnused, random_state=42).barcode
	checkUnusedSequences = [[barcode[i:i+20] for i in xrange(0, len(barcode)-20 + 1)] for barcode in sample_barcodes]
	checkUnusedSequences = [reverse_complement(sequence) for sublist in checkUnusedSequences for sequence in sublist]
	for barcode, probes in probeDict.iteritems():
		probeDict[barcode].extend(getMinHamming(probes[0:4], checkUnusedSequences))
	header.append("minMatchCheckedUnused")
    
I1 = args.initiators[0].upper()
I2 = args.initiators[1].upper()

for barcode, probes in probeDict.iteritems():
    probeDict[barcode][0:args.number] = addSplitInitiators(probes[0:args.number], I1, I2)

barcodeNumbersSorted = sorted([int(re.search(r'\d+', i).group()) for i in probeDict.keys()])

if args.outFileName is not None:
	outFile = args.outFileName + ".csv"
else:
	outFile = args.sample + ".csv"

with open(os.path.join(oligoPath, outFile), 'w') as out:
	out.write(",".join(header))
	out.write("\n")
	for i, barcode in enumerate(barcodeNumbersSorted):
		for j in xrange(0, args.number):
			out.write(",".join(["barcode{}_{}".format(barcode, j+1)] + [str(probeDict["barcode{}".format(barcode)][k]) for k in xrange(j, len(probeDict["barcode{}".format(barcode)]), args.number)] + ["\n"]))

if args.fullLengthSequence:
	barcodeList = []
	fastaPath = os.path.join(args.path, 'barcodeDesign', args.sample, 'fastaFiles/')
	for i in barcodeNumbersSorted:
		with open(os.path.join(fastaPath, "barcode{}.fa".format(i)), 'r') as barcodeFasta:
			barcodeFasta.readline()
			barcodeList.append(barcodeFasta.readline().strip("/n"))
	targetBarcodeFile = args.sample + "_targetBarcodes.txt"
	with open(os.path.join(oligoPath, targetBarcodeFile), 'w') as out:
		out.write("name\tbarcode")
		for i, barcode in enumerate(barcodeNumbersSorted):
			out.write("\n" + "barcode{}".format(barcode) + "\t" + barcodeList[i])


