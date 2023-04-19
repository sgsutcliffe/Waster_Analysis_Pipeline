import urllib.request
import os
import sys
import subprocess
import requests
import pandas as pd
import yaml

#NOTE: This is modification of https://github.com/andersen-lab/Freyja Freyja update command. I created this specifically just to bypass issues I was having
# with urllib.request on one server

def download_tree(locDir):
	url = "http://hgdownload.soe.ucsc.edu/goldenPath/wuhCor1/"\
		  "UShER_SARS-CoV-2/public-latest.all.masked.pb.gz"
	treePath = os.path.join(locDir, "public-latest.all.masked.pb.gz")
	urllib.request.urlretrieve(url, treePath)
	return treePath


def convert_tree(locDir):
	print(locDir)
	treePath = os.path.join(locDir, "public-latest.all.masked.pb.gz")
	varCmd = f"matUtils extract -i {treePath} -C lineagePaths.txt -d {locDir}"
	sys.stdout.flush()  # force python to flush
	completed = subprocess.run(varCmd, shell=True, executable="/bin/bash",
							   stdout=subprocess.DEVNULL)
	return completed


def get_curated_lineage_data(locDir):
	url2 = "https://raw.githubusercontent.com/outbreak-info/outbreak.info/"\
		   "master/web/src/assets/genomics/curated_lineages.json"
	urllib.request.urlretrieve(url2,
							   os.path.join(locDir,
											"curated_lineages.json"))


def get_cl_lineages(locDir):
	# for now, use lineages metadata created using patch
	#r = requests.get('https://raw.githubusercontent.com/outbreak-info/' +
					 #'outbreak.info/master/curated_reports_prep/lineages.yml')
	os.system("wget -O {0}/lineages.yml https://raw.githubusercontent.com/outbreak-info/outbreak.info/master/curated_reports_prep/lineages.yml".format(locDir))
	# r = requests.get('https://raw.githubusercontent.com/cov-lineages' +
	#                  '/lineages-website/master/data/lineages.yml')
	#if r.status_code == 200:
		#with open(os.path.join(locDir, 'lineages.yml'), 'w+') as f:
			#f.write(r.text)

def parse_tree_paths(df):
	df = df.set_index('clade')
	# Make sure to check with new tree versions, lineages could get trimmed.
	df = df.drop_duplicates(keep='last')
	df['from_tree_root'] = df['from_tree_root'].fillna('')
	df['from_tree_root'] = df['from_tree_root']\
		.apply(lambda x: x.replace(' ', '').strip('>').split('>'))
	return df

def convert_to_barcodes(df):
	# builds simple barcodes, not accounting for reversions
	df_barcodes = pd.DataFrame()
	for clade in df.index:
		# sparse,binary encoding
		cladeSeries = pd.Series({c: df.loc[clade, 'from_tree_root']
									  .count(c) for c in
								 df.loc[clade, 'from_tree_root']}, name=clade)
		df_barcodes = pd.concat((df_barcodes, cladeSeries), axis=1)

	print('separating combined splits')
	df_barcodes = df_barcodes.T
	df_barcodes = df_barcodes.drop(columns='')
	df_barcodes = df_barcodes.fillna(0)
	temp = pd.DataFrame()
	dropList = []
	for c in df_barcodes.columns:
		# if column includes multiple mutations,
		# split into separate columns and concatenates
		if "," in c:
			for mt in c.split(","):
				if mt not in temp.columns:
					temp = pd.concat((temp, df_barcodes[c].rename(mt)),
									 axis=1)
				else:
					# to handle multiple different groups with mut
					temp[mt] += df_barcodes[c]
			dropList.append(c)
	df_barcodes = df_barcodes.drop(columns=dropList)
	df_barcodes = pd.concat((df_barcodes, temp), axis=1)
	df_barcodes = df_barcodes.groupby(axis=1, level=0).sum()
	return df_barcodes

def reversion_checking(df_barcodes):

	print('checking for mutation pairs')
	# check if a reversion is present.
	flipPairs = [(d, d[-1] + d[1:len(d)-1]+d[0]) for d in df_barcodes.columns
				 if (d[-1] + d[1:len(d)-1]+d[0]) in df_barcodes.columns]
	flipPairs = [list(fp) for fp in list(set(flipPairs))]
	# subtract lower of two pair counts to get the lineage defining mutations
	for fp in flipPairs:
		df_barcodes[fp] = df_barcodes[fp].subtract(df_barcodes[fp].min(axis=1),
												   axis=0)
	# drop all unused mutations (i.e. paired mutations with reversions)
	df_barcodes = df_barcodes.drop(
		columns=df_barcodes.columns[df_barcodes.sum(axis=0) == 0])
	return df_barcodes

def check_mutation_chain(df_barcodes):
	# case when (non-reversion) mutation happens in site with existing mutation
	seq_muts = identify_chains(df_barcodes)
	while len(seq_muts) > 0:
		# combine mutations string into single mutation
		for i, sm in enumerate(seq_muts):
			lin_seq = df_barcodes[(df_barcodes[sm[0]] > 0) &
								  (df_barcodes[sm[1]] > 0)]
			if sm[2] not in df_barcodes.columns:
				# combination leads to new mutation
				newCol = pd.Series([(1 if dfi in lin_seq[0:2] else 0)
								   for dfi in df_barcodes.index], name=sm[2],
								   index=df_barcodes.index)
				df_barcodes = pd.concat([df_barcodes, newCol], axis=1)
			else:
				# combining leads to already existing mutation
				# just add in that mutation
				df_barcodes.loc[lin_seq.index, sm[2]] = 1
			# remove constituent mutations
			df_barcodes.loc[lin_seq.index, sm[0:2]] -= 1

		# drop all unused mutations
		df_barcodes = df_barcodes.drop(
			columns=df_barcodes.columns[df_barcodes.sum(axis=0) == 0])
		seq_muts = identify_chains(df_barcodes)
	return df_barcodes
def identify_chains(df_barcodes):

	sites = [d[0:len(d) - 1]for d in df_barcodes.columns]
	flip_sites = [d[-1] + d[1:len(d) - 1]for d in df_barcodes.columns]
	# for each mutation, find possible sequential mutations
	seq_muts = [[d, df_barcodes.columns[j], d[0:len(d) - 1] +
				 df_barcodes.columns[j][-1]]
				for i, d in enumerate(df_barcodes.columns)
				for j, d2 in enumerate(sites)
				if ((flip_sites[i] == sites[j]) and
					(d[-1] + d[1:len(d) - 1] + d[0]) !=
					df_barcodes.columns[j])]

	# confirm that mutation sequence is actually observed
	seq_muts = [sm for sm in seq_muts if df_barcodes[(df_barcodes[sm[0]] > 0) &
				(df_barcodes[sm[1]] > 0)].shape[0] > 0]

	mut_sites = [sortFun(sm[2]) for sm in seq_muts]
	# return only one mutation per site for each iteration
	seq_muts = [seq_muts[i] for i, ms in enumerate(mut_sites)
				if ms not in mut_sites[:i]]
	return seq_muts

def sortFun(x):
	# sort based on nuc position, ignoring nuc identities
	return int(x[1:(len(x)-1)])

if __name__ == '__main__':
	locDir = sys.argv[1]
   
	# # get data from UShER
	print('Downloading a new global tree')
	download_tree(locDir)
	print('Getting outbreak data')
	get_curated_lineage_data(locDir)
	print("Converting tree info to barcodes")
	convert_tree(locDir)  # returns paths for each lineage
	# Now parse into barcode form
	lineagePath = os.path.join(locDir, "lineagePaths.txt")
	print('Building barcodes from global phylogenetic tree')
	df = pd.read_csv(lineagePath, sep='\t')
	print('Parse Tree Paths')
	df = parse_tree_paths(df)
	print('Convert to barcodes')
	df_barcodes = convert_to_barcodes(df)
	print('Reversion Checking')
	df_barcodes = reversion_checking(df_barcodes)
	print('Check Mutation Chain')
	df_barcodes = check_mutation_chain(df_barcodes)


	# get lineage metadata from cov-lineages
	print('get lineage metadata from cov-lineages')
	get_cl_lineages(locDir)
	# as default:
	# since usher tree can be ahead of cov-lineages,
	# we drop lineages not in cov-lineages
	noncl=True
	if noncl:
		# read linages.yml file
		with open(os.path.join(locDir, 'lineages.yml'), 'r') as f:
			try:
				lineages_yml = yaml.safe_load(f)
			except yaml.YAMLError as exc:
				raise ValueError('Error in lineages.yml file: ' + str(exc))
		lineageNames = [lineage['name'] for lineage in lineages_yml]
		df_barcodes = df_barcodes.loc[df_barcodes.index.isin(lineageNames)]
	else:
		print("Including lineages not yet in cov-lineages.")
	down_date = subprocess.check_output("curl http://hgdownload.soe.ucsc.edu/goldenPath/wuhCor1/UShER_SARS-CoV-2/public-latest.version.txt | awk -F'[()]' '{print $2}'", shell=True)
	down_date = down_date.decode("utf-8").split("\n")
	down_date = down_date[0]
	barcode = "usher_barcodes_" + down_date + ".csv"
	df_barcodes.to_csv(os.path.join(locDir, barcode))
	# delete files generated along the way that aren't needed anymore
	print('Cleaning up')
	os.remove(lineagePath)
	os.remove(os.path.join(locDir, "public-latest.all.masked.pb.gz"))
