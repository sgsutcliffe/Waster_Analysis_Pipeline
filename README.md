# Running Wastewater Analysis Instructions
The pipeline is largely using Freyja: https://github.com/andersen-lab/Freyja

Dependencies:
- Singularity > 3.0 (tested on 3.6.4)
- Python 3 (tested on 3.7.7)

Requirements:
- Running USHER barcode updates was tested with at least 8GB of memory. (If you get error lineagePaths.txt not found likely a memory issue)

## January 19 Updates
- Added in two steps for Quality control 1) QC_parallelization_V2.py 2) file_checking_V1.py [In Development] (more below)
- Updated the pipeline script to version 4.2 Freyja_parallelization_V4.2.py
   - This version reduces the number of intermediate files and switches to compressed fasta/fastq files
   - Added a "-update/-fupdate" option to turn on usher-barcode updates
   - Does not include the Freyja visualization command
- Updated the Singularity container (Freyja_V6.sif) to accomodate the QC pipeline

## Required Files for Running

In the workspace directory, or the directory where you store all the files Freyja pipeline needs to run:

Files required:

* Freyja_parallelization_V4.2.py #Python script for parallelization execution, Freyja update, and Freyja. Runs eight samples simultaneously
* sample_list #This you will need to make yourself depending on the samples [See more information below]
* usher_update_V2.py #This is a modified version of Freyja's update function to fix some bugs that came up running it on some servers. I would recommend running 'freyja update' instead
* QC_parallelization_V2.py #This generates a multiQC file and a number of files with information on run
* file_checking_V1.py #This simply checks that all the files have been generated and if freyja output meets a minimum criteria

Files if not downloaded will be downloaded:    
   Note: The downloading of human genome & building bwa index files take a while. I'd suggest running this first without any samples before analyzing samples. WARNING: I use wget to connect to the websites. If you need a more secure file-transfer download them prior to running script.
* Homo_sapiens.GRCh38.fa/.fa.amb/.fa.ann/.fa.bwt/.fa.pac/.fa.sa/ # BWA index for human genome
* MN908947_3.fasta/.amb/.ann/.bwt/.fai/.pac/.fasta.sa/.gb #BWA index of the reference Wuhan strain Accession: MN908947 
* SARS-CoV-2.primer.bed #Artic V4.1 primer BED file for iVar primer trimming
* Kraken2wViruses #Kraken2 database built with contaminants the user wants to look for. Instructions below

You'll also need the container of singularity for Freyja

* Freyja_V6.sif #You'll need to build with sudo permissions
* Freyja_Definition_File_V6 #This is the definition file for building the container

### Building singularity container

You'll need Singularity Version 3 or greater installed and root permissions

```shell

sudo singularity build Freyja_V6.sif Freyja_Definition_File_V6

```
Note: This creates a compressed read-only squashfs file system suitable for production. If you want to have a writable file-system (writable ext3 or (ch)root directory) try the options --writable or --sandbox. Respectively. 

### Building Kraken2 database

```shell
singularity exec --no-home /path/to/container/Freyja_V6.sif kraken2-build --standard --db /path/to/run/location/Kraken2wViruses
```
Note: This will build the entire Kraken2 database which is quite large and require a lot of memory to build (~100GB). For instructions on customizing the build and speeding up the process using multiple-threads see https://github.com/DerrickWood/kraken2/wiki/Manual I would recommend including all viruses and human-genome in the build at the very least.

For users of digital alliance. If you add mugqic modules to your profile (https://genpipes.readthedocs.io/en/genpipes-v4.4.0/deploy/access_gp_pre_installed.html) Then you can use the module mugqic/kraken2/2.1.0 and point to /cvmfs/soft.mugqic/CentOS6/software/kraken2/kraken2-2.1.0/db which does not have the Wu-Han SARS-CoV-2 genome but one that is very close.

### Recipe for making sample list

The paired reads that come from C3G have the extensions and right now the pipeline expects this:
R1 = <sample_name>_R1_001.fastq.gz
R2 = <sample_name>_R2_001.fastq.gz

Note: Sometimes samples are run in two different lanes and need to be merged. 

The 'sample_list' file is just a text file with all the <sample_name> involved in seperate line. I use a quick bash one liner to make the list

```shell
ls <path>/<to>/<reads>/*.fastq.gz | sed "s/<path>/<to>/<reads>\///" | sed "s/_R[0-9]_001.fastq.gz//" | sort | uniq > <path>/<to>/<workspace>/sample_list
```

## Running Freyja using the singularity container
Note: The pipeline is parallel in the sense it runs 8 samples at a time, regardless of how many blocks-of-memory/threads are available. This will be updated in the snakemake workflow. But keep this in mind when selecting threads per sample and how much memory you allocate per sample.

Right now the order of variables and location of where it is run is very important.

Where you execute the command is also important. You'll need to execute the singularity command in the parent directory of all the folders because you will need to bind this folder and all its sub-folders into the containers /mnt directory.

![](directory_example.jpeg)

For more information on mounting directories see: https://docs.sylabs.io/guides/3.0/user-guide/bind_paths_and_mounts.html
But when creating variables to run the pipeline do not change the '/mnt' in the path

If you don't have any usherbarcodes already downloaded you can just put:
'usherbarcode.csv' and add the option to either -update/-fupdate at the end of the command (see below)

Note: Order of the parameters matters
```shell
mounted_directory=<mounted_directory_name>
container=/path/to/singularity_container/Freyja_V6.sif
run_location=/mnt/path/to/workspace/directory/
sample_location=/mnt/path/to/reads/
sample_list=/path/to/sample/list/<sample_list_file>
threads_per_sample=<interger>
barcode=<usher_barcode_file>
output_directory=/mnt/<output_folder_name>

singularity exec --no-home -B ${mounted_directory}:/mnt \
${container} python3 \
${run_location}Freyja_parallelization_V4.2.py ${run_location} ${sample_location} ${sample_list} ${threads_per_sample} ${barcode} ${output_directory}

```
Barcode update options (include at the end of command):
-update : uses the modified freyja update command, less secure but I have confirmed that it can be run on multiple OS/servers
-fupdate : uses the built-in freyja update command, this is still-in development, as it breaks if it cannot make a secure connection to hosted databases
If no option is present it will simply run whichever barcode the user specified. Barcodes are updated daily, and it will warn you if the barcode is out-of-date.


## Running the Quality-Control pipeline

The input_directory : This is the output_directory of the previous step
The new output_directory : This is where you want to the QC files to go

```shell
mounted_directory=<mounted_directory_name>
container=/path/to/singularity_container/Freyja_V6.sif
run_location=/mnt/path/to/workspace/directory/
sample_location=/mnt/path/to/reads/
sample_list=/path/to/sample/list/<sample_list_file>
threads_per_sample=<interger>
barcode=<usher_barcode_file>
output_directory=/mnt/<output_folder_name>
input_directory=/mnt/<input_folder_name>

singularity exec --no-home -B ${mounted_directory}:/mnt \
${container} python3 \
${run_location}QC_parallelization_V2.py ${run_location} ${sample_location} ${sample_list} ${threads_per_sample} ${barcode} ${output_directory}

```
Note: MultiQC, taking all the information and putting it into one html file, takes a lot of tmp memory. If you have a lot of samples I suggest making a tmp folder to mount. eg. your/var/tmp:/var/tmp,your/tmp:/tmp That way you'll have whatever space is available on your machine.

## In Development

## File checking (Not Working Currently)
file_check_V1.py is a scipt that looks for all the outputs of the files and puts it into a CSV file. This is still in development and does not work. I need change the path to files in the script to make it work. Also it requires samtools be installed. Samtools is installed in the singularity container, but I do not have instructions yet written for this. The same goes for file_check_visualize.R which visualizes this output.[Soon to come]

## Visualization of Freyja output

Freyja has a visualization feature pre-installed. This is not an option for the pipeline. I think some cleaning up of lineage-calls should be done before visuallizing. The scripts I have written to tackle this require too much manual curation to make available. If you are interested contact me sgsutcliffe[at]gmail.com 

## I will be adding Kraken2 database path as option to allow users to point to databases downloaded elsewhere

## I am also going to add an ouput that tracks nonsynonmous mutations found in wastewater 

## I will also be looking to generate a table output of key QC-metrics for tracking sample quality.

## Lastly I will be putting this into a workflow manager (e.g. Snakemake)






