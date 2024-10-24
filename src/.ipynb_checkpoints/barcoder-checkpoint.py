from reader import read_file
import os, csv, sys, yaml, time, functools, builtins
from resilience_tracker import check_resilience
from flow_tracker import check_flow
from coarse_tracker import check_coarse
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib import gridspec
from writer import write_file, gen_combined_barcode

def check_channel_dim(image):
    min_intensity = np.min(image)
    mean_intensity = np.mean(image)
    return 2 * np.exp(-1) * mean_intensity <= min_intensity

def execute_htp(filepath, config_data):
    reader_data = config_data['reader']
    save_intermediates = config_data['writer']['return_intermediates']
    accept_dim_channel, accept_dim_im, channel_select, coarsening, flow, resilience, return_graphs, verbose = reader_data.values()
    r_data = config_data['resilience_parameters']
    f_data = config_data['flow_parameters']
    c_data = config_data['coarse_parameters']
    stitch_barcode = config_data['writer']['stitch_barcode']
    
    print = functools.partial(builtins.print, flush=True)
    vprint = print if verbose else lambda *a, **k: None

    def check(channel, resilience, flow, coarse, resilience_data, flow_data, coarse_data):
        figure_dir_name = remove_extension(filepath) + ' BARCODE Output'
        fig_channel_dir_name = os.path.join(figure_dir_name, 'Channel ' + str(channel))
        if not os.path.exists(figure_dir_name):
            os.makedirs(figure_dir_name)
        if not os.path.exists(fig_channel_dir_name):
            os.makedirs(fig_channel_dir_name)
        
        if resilience == True:
            r_offset = resilience_data['r_offset']
            f_step = resilience_data['frame_step']
            f_start, f_stop = resilience_data['evaluation_settings'].values()
            rfig, void_value, spanning, island_size, island_movement, void_growth = check_resilience(file, fig_channel_dir_name, channel, r_offset, f_step, f_start, f_stop, save_intermediates, verbose)
        else:
            rfig = None
            spanning = None
            void_value = None
            island_size = None
            island_movement = None
            void_growth = None
        if flow == True:
            downsample, frame_step, frame_interval, nm_pix_ratio = flow_data.values()
            direct, directSD, avg_vel, avg_speed, avg_div = check_flow(file, fig_channel_dir_name, channel, int(frame_step), downsample, frame_interval, nm_pix_ratio, return_graphs, save_intermediates, verbose)
        else:
            direct = None
            directSD = None
            avg_vel = None
            avg_speed = None
            avg_div = None
        if coarse == True:
            fframe, lframe = coarse_data['evaluation_settings'].values()
            percent_frames = coarse_data['mean_mode_frames_percent']
            perc_increase, cfig, max_kurt, max_skew, max_mean_mode, kurt_diff, skew_diff = check_coarse(file, fig_channel_dir_name, channel, fframe, lframe, percent_frames, save_intermediates, verbose)
        else:
            perc_increase = None
            cfig = None
            max_kurt = None
            max_skew = None 
            max_mean_mode = None
            kurt_diff = None
            skew_diff = None

        figpath = os.path.join(fig_channel_dir_name, 'Summary Graphs.png')
        if return_graphs == True:
            fig = plt.figure(figsize = (15, 5))
            gs = gridspec.GridSpec(1,3)

            if rfig != None:
                ax1 = rfig.axes[0]
                ax1.remove()
                ax1.figure = fig
                fig.add_axes(ax1)
                ax1.set_position([2.5/15, 1/10, 4/5, 4/5])

            if cfig != None:               
                ax3 = cfig.axes[0]
                ax3.remove()
                ax3.figure = fig
                fig.add_axes(ax3)
                ax3.set_position([32.5/15, 1/10, 4/5, 4/5])

            plt.savefig(figpath)
            plt.close(fig)
        plt.close('all')

        result = [channel, spanning, island_size, void_value, void_growth, max_kurt, max_skew, max_mean_mode, perc_increase, kurt_diff, skew_diff, avg_vel, avg_speed, avg_div, island_movement, direct, directSD]

        vprint('Channel Screening Completed')
            
        return result
    
    file = read_file(filepath, accept_dim_im)


    if (isinstance(file, np.ndarray) == False):
        raise TypeError("File was not of the correct filetype")

    channels = min(file.shape)
    
    rfc = []
    barcodes = []
    if channel_select == 'All':
        vprint('Total Channels:', channels)
        for channel in range(channels):
            vprint('Channel:', channel)
            if check_channel_dim(file[:,:,:,channel]) and not accept_dim_channel:
                vprint('Channel too dim, not enough signal, skipping...')
                continue
            elif check_channel_dim(file[:,:,:,channel]) and accept_dim_channel:
                vprint('Warning: channel is dim. Accuracy of screening may be limited by this.')
                results = check(channel, resilience, flow, coarsening, r_data, f_data, c_data)
                results.insert(1, 1) # Indicate dim channel flag present
            else:
                results = check(channel, resilience, flow, coarsening, r_data, f_data, c_data)
                results.insert(1, 0) # Indicate no flags present
            rfc.append(results)
    
    else:
        while channel_select < 0:
            channel_select = channels + channel_select # -1 will correspond to last channel, etc
        if channel_select >= channels:
            channel_select = channels - 1 # Sets channel to maximum channel if channel selected is out of range
        vprint('Channel: ', channel_select)
        if check_channel_dim(file[:,:,:,channel_select]):
            vprint('Warning: channel is dim. Accuracy of screening may be limited by this.')
            results = check(channel_select, resilience, flow, coarsening, r_data, f_data, c_data)
            results.insert(1, 1) # Indicate dim channel flag present
        else:
            results = check(channel, resilience, flow, coarsening, r_data, f_data, c_data)
            results.insert(1, 0) # Indicate no flags present
        rfc.append(results)

    return rfc

def remove_extension(filepath):
    if filepath.endswith('.tiff'):
        return filepath.removesuffix('.tiff')
    if filepath.endswith('.tif'):
        return filepath.removesuffix('.tif')
    if filepath.endswith('.nd2'):
        return filepath.removesuffix('.nd2')

def process_directory(root_dir, config_data):
    verbose = config_data['reader']['verbose']
    writer_data = config_data['writer']
    normalize_data, save_intermediates, stitch_barcode = writer_data.values()
    print = functools.partial(builtins.print, flush=True)
    vprint = print if verbose else lambda *a, **k: None
    
    if os.path.isfile(root_dir):
        all_data = []
        file_path = root_dir
        filename = os.path.basename(file_path)
        dir_name = os.path.dirname(file_path)
        
        time_filepath = os.path.join(dir_name, filename + 'time.txt')
        time_file = open(time_filepath, "w", encoding="utf-8")
        time_file.write(file_path + "\n")
        start_time = time.time()
        rfc_data = execute_htp(file_path, config_data)
        if rfc_data == None:
            raise TypeError("Please input valid file type ('.nd2', '.tiff', '.tif')")
        all_data.append([filename])
        all_data.extend(rfc_data)
        all_data.append([])
        filename = remove_extension(filename) + '_'
        end_time = time.time()
        elapsed_time = end_time - start_time
        vprint('Time Elapsed:', elapsed_time)
        time_file.write('Time Elapsed: ' + str(elapsed_time) + "\n")
        output_filepath = os.path.join(dir_name, filename + ' summary.csv')
        write_file(output_filepath, all_data)
        
        if stitch_barcode:
            output_figpath = os.path.join(dir_name, filename + ' summary barcode')
            gen_combined_barcode(np.array(rfc_data), output_figpath, normalize_data)

        settings_loc = os.path.join(dir_name, filename + " settings.yaml")
        with open(settings_loc, 'w+', encoding="utf-8") as ff:
            yaml.dump(config_data, ff)

        time_file.close()
            
    else: 
        all_data = []
        all_rfc_data = []
        time_filepath = os.path.join(root_dir, os.path.basename(root_dir) + ' time.txt')
        time_file = open(time_filepath, "w", encoding="utf-8")
        time_file.write(root_dir + "\n")
        
        start_folder_time = time.time()
        
        for dirpath, dirnames, filenames in os.walk(root_dir):

            dirnames[:] = [d for d in dirnames]
    
            for filename in filenames:
                if filename.startswith('._'):
                    continue
                file_path = os.path.join(dirpath, filename)
                start_time = time.time()
                try:
                    rfc_data = execute_htp(file_path, config_data)
                except TypeError:
                    continue
                except Exception as e:
                    with open(os.path.join(root_dir, "failed_files.txt"), "a", encoding="utf-8") as log_file:
                        log_file.write(f"File: {file_path}, Exception: {str(e)}\n")
                    continue
                if rfc_data == None:
                    continue
                all_data.append([file_path])
                all_data.extend(rfc_data)
                all_data.append([])
                for result in rfc_data:
                    all_rfc_data.append(np.array(result))

                end_time = time.time()
                elapsed_time = end_time - start_time
                vprint('Time Elapsed:', elapsed_time)
                time_file.write(file_path + "\n")
                time_file.write('Time Elapsed: ' + str(elapsed_time) + "\n")
        
        output_filepath = os.path.join(root_dir, os.path.basename(root_dir) + " Summary.csv")
        write_file(output_filepath, all_data)
        
        # print(all_rfc_data)
        
        if stitch_barcode:
            output_figpath = os.path.join(root_dir, os.path.basename(root_dir) + '_Summary Barcode')
            gen_combined_barcode(np.array(all_rfc_data), output_figpath, normalize_data)

        end_folder_time = time.time()
        elapsed_folder_time = end_folder_time - start_folder_time
        vprint('Time Elapsed to Process Folder:', elapsed_folder_time)
        time_file.write('Time Elapsed to Process Folder: ' + str(elapsed_folder_time) + "\n")

        settings_loc = os.path.join(root_dir, os.path.basename(root_dir) + "settings.yaml")
        with open(settings_loc, 'w+') as ff:
            yaml.dump(config_data, ff)