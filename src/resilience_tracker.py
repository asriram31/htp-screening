from reader import read_file
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import imageio.v3 as iio
from nd2reader import ND2Reader
import math, pims, yaml, gc, csv, os, glob, pickle, functools, builtins
from numpy.polynomial import Polynomial

from skimage import measure, io
from skimage.measure import label, regionprops

from scipy import ndimage

class MyException(Exception):
    pass

def binarize(frame, offset_threshold = 0.1):
    avg_intensity = np.mean(frame)
    threshold = avg_intensity * (1 + offset_threshold)
    new_frame = np.where(frame < threshold, 0, 1)
    return new_frame

def top_ten_average(lst):
    lst.sort(reverse=True)
    length = len(lst)
    top_ten_percent = int(np.ceil(length * 0.1))
    return np.mean(lst[0:top_ten_percent])

def check_span(frame):

    def check_connected(frame, axis=0):
        # Ensures that either connected across left-right or up-down axis
        if axis == 0:
            first = (frame[0] == 1).any()
            last = (frame[-1] == 1).any()
        elif axis == 1:
            first = (frame[:,0] == 1).any()
            last = (frame[:,-1] == 1).any()
        else:
            raise Exception("Axis must be 0 or 1.")
    
        struct = ndimage.generate_binary_structure(2, 2)
    
        frame_connections, num_features = ndimage.label(input=frame, structure=struct)
    
        if axis == 0:
            labeled_first = np.unique(frame_connections[0,:])
            labeled_last = np.unique(frame_connections[-1,:])
    
        if axis == 1:
            labeled_first = np.unique(frame_connections[:,0])
            labeled_last = np.unique(frame_connections[:,-1])
    
        labeled_first = set(labeled_first[labeled_first != 0])
        labeled_last = set(labeled_last[labeled_last != 0])
        
        if labeled_first.intersection(labeled_last):
            return 1
        else:
            return 0
    
    return (check_connected(frame, axis = 0) or check_connected(frame, axis = 1))

def track_void(image, name, threshold, step, return_graphs, save_intermediates):
    downsample = 4
    xindices = np.arange(0, image[0].shape[0], downsample)
    yindices = np.arange(0, image[0].shape[1], downsample)
        
    def find_largest_void(frame, find_void = True):      
        if find_void:
            frame = np.invert(frame)
            
        labeled, a = label(frame, connectivity= 2, return_num =True) # identify the regions of connectivity 2
        if a == 0:
            return frame.shape[0] * frame.shape[1]
        
        regions = regionprops(labeled) # determines the region properties of the labeled
        if not regions:
            return frame.shape[0] * frame.shape[1]
        
        largest_region = max(regions, key = lambda r: r.area) # determines the region with the maximum area
        return largest_region.area # returns largest region area

    def largest_island_position(frame):      
        labeled, a = label(frame, connectivity = 2, return_num =True) # identify the regions of connectivity 2
        if a == 0:
            return None
        regions = regionprops(labeled) # determines the region properties of the labeled
        largest_region = max(regions, key = lambda r: r.area) # determines the region with the maximum area
        return largest_region.centroid # returns largest region area
        
    if save_intermediates:
        filename = os.path.join(name, 'BinarizationData.csv')
        f = open(filename, 'w')
        csvwriter = csv.writer(f)
        
    void_lst = []
    island_area_lst = []
    island_position_lst = []
    connected_lst = []
    region_lst = []
    
    save_spots = np.linspace(0, len(image), 3)
    
    for i in range(0, len(image), step):
        new_image = image[i][xindices][:,yindices]
        new_frame = binarize(new_image, threshold)
        
        if i in save_spots and return_graphs:
            compare_fig, comp_axs = plt.subplots(ncols = 2, figsize=(10, 5))
            comp_axs[0].imshow(new_image, cmap='gray')
            comp_axs[1].imshow(new_frame, cmap='gray')
            plt.savefig(os.path.join(name, 'Binarization Frame ' + str(i) + ' Comparison.png'))
            plt.close('all')
            
        if save_intermediates:
            csvwriter.writerow([str(i)])
            csvwriter.writerows(new_frame)
            csvwriter.writerow([])
        
        void_lst.append(find_largest_void(new_frame))
        island_area_lst.append(find_largest_void(new_frame, find_void = False))
        island_position_lst.append(largest_island_position(new_frame))
        connected_lst.append(check_span(new_frame))
        
        labeled, a = label(new_frame, connectivity = 2, return_num =True) # identify the regions of connectivity 2

        regions = regionprops(labeled) # determines the region properties of the labeled
        
        region_lst.append(regions)
    i = len(image) - 1    
    if i % step != 0:
        new_image = image[i][xindices][:,yindices]
        new_frame = binarize(new_image, threshold)
        
        if i in save_spots and return_graphs:
            compare_fig, comp_axs = plt.subplots(2, figsize=(10, 5))
            comp_axs[0].imshow(new_image)
            comp_axs[1].imshow(new_frame)
            plt.save(os.path.join(name, 'Binarization Frame ' + str(i) + ' Comparison.png'))
        
        if save_intermediates:
            csvwriter.writerow([str(i)])
            csvwriter.writerows(new_frame)
            csvwriter.writerow([])
        
        void_lst.append(find_largest_void(new_frame))
        island_area_lst.append(find_largest_void(new_frame, find_void = False))
        island_position_lst.append(largest_island_position(new_frame))
        connected_lst.append(check_span(new_frame))

    if save_intermediates:
        f.close()

    return void_lst, island_area_lst, island_position_lst, connected_lst, region_lst

def check_resilience(file, name, channel, R_offset = 0.1, frame_step = 10, frame_start_percent = 0.9, frame_stop_percent = 1, return_graphs = False, save_intermediates = False, verbose = True):
    print = functools.partial(builtins.print, flush=True)
    vprint = print if verbose else lambda *a, **k: None
    vprint('Beginning Resilience Testing...')
    #Note for parameters: frame_step (stepsize) used to reduce the runtime. 
    image = file[:,:,:,channel]
    frame_initial_percent = 0.05

    fig, ax = plt.subplots(figsize = (5,5))

    # Error Checking: Empty Image
    if (image == 0).all():
        return [None] * 6
    
    while len(image) <= frame_step:
        frame_step = frame_step / 5
    
    largest_void_lst, island_area_lst, island_position_lst, connected_lst, r_lst = track_void(image, name, R_offset, frame_step, return_graphs, save_intermediates)
    start_index = int(np.floor(len(image) * frame_start_percent / frame_step))
    stop_index = int(np.ceil(len(largest_void_lst) * frame_stop_percent))
    start_initial_index = int(np.ceil(len(image)*frame_initial_percent / frame_step))

    void_gain_initial_list = np.mean(largest_void_lst[0:start_initial_index])
    void_percent_gain_list = np.array(largest_void_lst)/void_gain_initial_list
    
    island_gain_initial_list = np.mean(island_area_lst[0:start_initial_index])
    island_percent_gain_list = np.array(island_area_lst)/island_gain_initial_list
    
    start_index = 0
    plot_range = np.arange(start_index * frame_step, stop_index * frame_step, frame_step)
    plot_range[-1] = len(image) - 1 if stop_index * frame_step >= len(image) else stop_index * frame_step
    ax.plot(plot_range, void_percent_gain_list[start_index:stop_index], c='b', label='Original Void Size Proportion')
    ax.plot(plot_range, island_percent_gain_list[start_index:stop_index], c='r', label='Original Island Size Proportion')
    ax.set_xticks(plot_range)
    if stop_index * frame_step >= len(image) != 0:
        ax.set_xlim(left=None, right=len(image) - 1)
    ax.set_xlabel("Frames")
    ax.set_ylabel("Fraction")


    downsample = 4
    
    img_dims = image[0].shape[0] * image[0].shape[1] / (downsample ** 2)
    
    avg_void_percent_change = np.mean(largest_void_lst[start_index:stop_index])/void_gain_initial_list
    max_void_size = top_ten_average(largest_void_lst)/img_dims
    
    avg_island_percent_change = np.mean(island_area_lst[start_index:stop_index])/island_gain_initial_list
    island_size = top_ten_average(island_area_lst)/img_dims
    if len(np.array(island_position_lst).shape) != 2:
        average_direction = 0
    else:
        island_movement = np.array(island_position_lst)[:-1,:] - np.array(island_position_lst)[1:,:]
        island_speed = np.linalg.norm(island_movement,axis = 1)
        island_direction = np.arctan2(island_movement[:,1],island_movement[:,0])
        thresh_speed = 15
        while len(island_direction[np.where(island_speed < thresh_speed)]) == 0:
            thresh_speed += 1
        island_direction = island_direction[np.where(island_speed < thresh_speed)]
        average_direction = np.average(island_direction)
    
    spanning = len([con for con in connected_lst if con == 1])/len(connected_lst)

    
    return fig, max_void_size, spanning, island_size, average_direction, avg_void_percent_change, avg_island_percent_change
