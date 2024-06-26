from reader import read_file
import numpy as np
import matplotlib.pyplot as plt
import cv2 as cv
from scipy.fft import fft2, ifft2
from scipy.interpolate import Akima1DInterpolator
from scipy import optimize

#Find the first point at which a spline interpolant for a set of correlator values descends below a certain threshold
def findRoot(xValues, yValues,threshold):
    interpolator = Akima1DInterpolator(xValues, yValues)
    return optimize.root_scalar(lambda arg: interpolator([arg])[0]-threshold ,bracket=[min(xValues),max(xValues)]).root

def check_flow(file, name, channel, min_corr_len, min_fraction, frame_stride, downsample, pix_size, bin_width, decay_threshold = 1/np.exp(1)):
    #Width of annuli in pixels
    pixel_bin_width = np.ceil(bin_width / pix_size)
    #Length at which to stop computing correlators
    max_len = 500
    #Length in pixels at which to cut off correlators
    max_pixel_len = np.rint(max_len / pix_size)
    #Cutoff magnitude to consider a vector to be null; also helps to avoid divide-by-zero errors
    flt_tol = 1e-10

    fig, ax = plt.subplots(figsize=(5,5))

    def normalVectors(velocities):
        #Find velocity directions
        def normalize(vector):
            magnitude = np.linalg.norm(vector)
            if magnitude == 0: return np.array([0,0])
            return np.where(magnitude > flt_tol, np.array(vector)/magnitude, np.array([0, 0]))
                
        normals = np.zeros_like(velocities)
        for i in range(0, velocities.shape[0]):
            for j in range(0, velocities.shape[1]):
                normals[i][j] = normalize(velocities[i][j])
    
        return normals

    if(len(file.shape) == 4):
            images = file[:,:,:,channel]
    else:
            images = file[:,:,:]
    positions = np.array([0, int(np.floor(len(images)/2)), len(images) - frame_stride - 1])

    # Error Checking: Empty Images
    if (images == 0).all():
       verdict = "Data not available for this channel."
       return verdict, fig

    xindices = np.arange(0, images[0].shape[0], downsample)
    yindices = np.arange(0, images[0].shape[1], downsample)

    radii = np.zeros((len(xindices),len(yindices)))
    for i in range(0,len(xindices)):
        for j in range(0,len(yindices)):
            radii[i][j] = np.sqrt(xindices[i]**2 + yindices[j]**2)

    #For each consecutive pair
    corrLens = np.zeros(len(images)-frame_stride)
    pos = 0
    xMeans = np.array([])
    yMeans = np.array([])
    
    for iter in range(0,len(images)-frame_stride,1):
        flow = cv.calcOpticalFlowFarneback(images[iter], images[iter+frame_stride], None, 0.5, 3, 20, 3, 5, 1.2, 0)
        directions = normalVectors(flow[xindices][:,yindices])
        dirX = directions[:,:,0]
        dirY = directions[:,:,1]
        xMeans = np.append(xMeans, dirX.mean())
        yMeans = np.append(yMeans, dirY.mean())
        if(np.isin(pos, positions)):
                downU = flow[:,:,0][xindices][:,yindices]
                downU = np.flipud(downU)
                downV = -1*flow[:,:,1][xindices][:,yindices]
                downV = np.flipud(downV)
                fig2, ax2 = plt.subplots(figsize=(10,10))
                q = ax2.quiver(xindices, yindices, downU, downV,color='blue')
                fig2.savefig(name + '_' + str(pos) + '.png')
                plt.close(fig2)
        xFFT = fft2(dirX)
        xConv = np.real(ifft2(np.multiply(xFFT,np.conjugate(xFFT))))
        yFFT = fft2(dirY)
        yConv = np.real(ifft2(np.multiply(yFFT,np.conjugate(yFFT))))
        convSum = np.add(xConv,yConv)
        means = np.array([])
        inRadii = np.array([])
        for i in range(0,int(max_pixel_len),int(pixel_bin_width)):
                inBin = convSum[(radii > i -.5*pixel_bin_width)&(radii < i + .5*pixel_bin_width)]
                if(len(inBin) > 0):
                        inRadii = np.append(inRadii, i)
                        means = np.append(means, inBin.mean()/convSum[0,0])
        try:
            corrLens[pos] = pix_size*findRoot(inRadii,means,decay_threshold)
        except ValueError:
            corrLens[pos] = 0
        pos += 1
    
    if(len(corrLens[corrLens>min_corr_len])/len(corrLens) > min_fraction):
        verdict = 1
    else:
        verdict = 0
    ax.plot(range(0,len(corrLens)),corrLens)

    print("x mean: ", xMeans.mean(), "\n")
    print("y mean: ", yMeans.mean(), "\n")
    
    return verdict, fig
