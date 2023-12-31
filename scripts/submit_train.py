import os

batch = """#!/bin/bash

#SBATCH --job-name=train
#SBATCH --nodes=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=32GB
#SBATCH --time=32:59:00
#SBATCH --gres=gpu:1
#SBATCH --mail-type=begin
#SBATCH --mail-type=end
#SBATCH --mail-user=siddharthmishra19@gmail.com

source ~/.bashrc
conda activate sbi-fermi
cd /scratch/sm8383/fermi-gce-flows/
"""

##########################
# Explore configurations #
##########################

batch_size_list = [256]
fc_dims_list = [[[-1, 1024], [1024, 128]]]
maf_num_transforms_list = [8]
maf_hidden_features_list = [128]
activations = ["relu"]
flow_activations = ["tanh"]
kernel_size_list = [6]
n_neighbours_list = [8]
conv_channel_configs = ["standard"]
laplacian_types = ["combinatorial"]
conv_types = ["chebconv"]
conv_source_list = ["deepsphere"]
aux_summaries = ["None"]
n_aux_list = [2]
density_estimator_list = ["maf"]
r_outer_list = [25]
normalize_pixel_list = [0]

# samples_list = ["ModelO_gamma_fix_thin_disk_rescale_1M", "ModelO_gamma_fix_rescale_1M", "ModelA_gamma_fix_thin_disk_rescale_1M", "ModelF_gamma_fix_thin_disk_rescale_1M", "ModelO_gamma_fix_thin_disk_rescale_new_ps_priors_1M", "ModelO_gamma_fix_thin_disk_negative_dm_prio_rescale_1M"]

samples_list = ["ModelO_gamma_fix_thin_disk_negative_dm_prio_rescale_1M"]


for n_neighbours in n_neighbours_list:
    for maf_num_transforms in maf_num_transforms_list:
        for maf_hidden_features in maf_hidden_features_list:
            for batch_size in batch_size_list:
                for fc_dims in fc_dims_list:
                    for activation in activations:
                        for kernel_size in kernel_size_list:
                            for laplacian_type in laplacian_types:
                                for conv_type in conv_types:
                                    for conv_channel_config in conv_channel_configs:
                                        for aux_summary, n_aux in zip(aux_summaries, n_aux_list):
                                            for conv_source in conv_source_list:
                                                for density_estimator in density_estimator_list:
                                                    for r_outer in r_outer_list:
                                                        for normalize_pixel in normalize_pixel_list:
                                                            for flow_activation in flow_activations:
                                                                for sample in samples_list:
                                                                    batchn = batch + "\n"
                                                                    batchn += "python -u train.py --sample train_{} --name gce_{} --maf_num_transforms {} --maf_hidden_features {} --fc_dims '{}' --batch_size {} --activation {} --kernel_size {} --laplacian_type {} --conv_type {} --conv_channel_config {} --aux_summary {} --n_aux {} --n_neighbours {} --conv_source {} --density_estimator {} --r_outer {} --normalize_pixel {} --flow_activation {} --num_workers 16 --max_num_epochs 30".format(sample, sample, maf_num_transforms, maf_hidden_features, fc_dims, batch_size, activation, kernel_size, laplacian_type, conv_type, conv_channel_config, aux_summary, n_aux, n_neighbours, conv_source, density_estimator, r_outer, normalize_pixel, flow_activation)
                                                                    fname = "batch/submit.batch"
                                                                    f = open(fname, "w")
                                                                    f.write(batchn)
                                                                    f.close()
                                                                    os.system("chmod +x " + fname)
                                                                    os.system("sbatch " + fname)

# ##################
# # Just summaries #
# ##################

# batch_size_list = [128]
# maf_num_transforms_list = [4, 12]
# maf_hidden_features_list = [128, 512]
# methods = ["snpe"]
# activations = ["relu"]
# summaries = ["pca_96", "pspec_4"]

# for maf_num_transforms in maf_num_transforms_list:
#     for maf_hidden_features in maf_hidden_features_list:
#         for batch_size in batch_size_list:
#             for method in methods:
#                 for activation in activations:
#                     for summary in summaries:
#                         batchn = batch + "\n"
#                         batchn += "python -u train.py --sample train_ModelO_gamma_fix_480k --name gce_ModelO_gamma_fix_480k --method {} --maf_num_transforms {} --maf_hidden_features {} --batch_size {} --activation {} --summary {}".format(method, maf_num_transforms, maf_hidden_features, batch_size, activation, summary)
#                         fname = "batch/submit.batch"
#                         f = open(fname, "w")
#                         f.write(batchn)
#                         f.close()
#                         os.system("chmod +x " + fname)
#                         os.system("sbatch " + fname)