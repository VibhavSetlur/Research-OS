#!/usr/bin/env nextflow

nextflow.enable.dsl = 2

/*
 * ChIP-seq pipeline: ERα binding-site analysis
 * MCF-7 vs T47D, 100 nM estradiol, 45 min stimulation
 *
 * FASTQC -> BWA -> MACS2_PEAKCALL -> MOTIF_ENRICH
 */

params.reads        = "$projectDir/data/*_{R1,R2}.fastq.gz"
params.genome       = "$projectDir/refs/hg38.fa"
params.bwa_index    = "$projectDir/refs/bwa/hg38"
params.outdir       = "results"
params.macs_gsize   = "hs"
params.macs_qvalue  = 0.01

process FASTQC {
    container 'biocontainers/fastqc:v0.12.1_cv1'
    cpus 2
    memory '4 GB'
    time '1h'

    input:
    tuple val(sample_id), path(reads)

    output:
    tuple val(sample_id), path("${sample_id}_fastqc.zip"), emit: qc

    script:
    """
    fastqc --threads ${task.cpus} ${reads} -o .
    """
}

process BWA {
    container 'biocontainers/bwa:v0.7.17_cv1'
    cpus 16
    memory '32 GB'
    time '6h'

    input:
    tuple val(sample_id), path(reads)
    path index

    output:
    tuple val(sample_id), path("${sample_id}.sorted.bam"), path("${sample_id}.sorted.bam.bai"), emit: bam

    script:
    """
    bwa mem -t ${task.cpus} ${index}/hg38 ${reads} \\
      | samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam -
    samtools index ${sample_id}.sorted.bam
    """
}

process MACS2_PEAKCALL {
    container 'biocontainers/macs2:v2.2.7.1_cv1'
    cpus 4
    memory '16 GB'
    time '2h'

    input:
    tuple val(sample_id), path(treatment_bam), path(treatment_bai), path(control_bam), path(control_bai)

    output:
    tuple val(sample_id), path("${sample_id}_peaks.narrowPeak"), emit: peaks

    script:
    """
    macs2 callpeak \\
      -t ${treatment_bam} \\
      -c ${control_bam} \\
      -f BAM \\
      -g ${params.macs_gsize} \\
      -q ${params.macs_qvalue} \\
      -n ${sample_id} \\
      --outdir .
    """
}

process MOTIF_ENRICH {
    container 'biocontainers/homer:v4.11_cv1'
    cpus 8
    memory '24 GB'
    time '3h'

    input:
    tuple val(sample_id), path(peaks)
    path genome

    output:
    tuple val(sample_id), path("${sample_id}_motifs/"), emit: motifs

    script:
    """
    findMotifsGenome.pl ${peaks} ${genome} ${sample_id}_motifs \\
      -size 200 -mask -p ${task.cpus}
    """
}

workflow {
    read_ch = Channel.fromFilePairs(params.reads, checkIfExists: true)
    FASTQC(read_ch)
    BWA(read_ch, file(params.bwa_index))
    // Pairing of treatment + input control happens upstream of MACS2.
    // MOTIF_ENRICH consumes the narrowPeak outputs of MACS2_PEAKCALL.
}
