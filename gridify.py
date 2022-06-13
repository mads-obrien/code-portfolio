# -*- coding: utf-8 -*-
"""
Created on Mon Sep 27 14:42:05 2021

Produce equal-area grid squares across an area of interest, 
and calculate the (mean, count, etc.) of a second data layer by grid square.


@author: maobrien
"""
#%% Import required packages
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
from datetime import datetime


def gridify(roi, length=4000, width=4000, clip2shape=True):
    '''
    Given a region of interest (ROI), 
    create a "fishnet" of grid polygons across the area, 
    with grid squares of a specified length and width,
    clipped to the shape of the region.
    DEPENDENCIES: geopandas, matplotlib, datetime
      
    ARGUMENTS:
    roi = Region Of Interest, i.e. geodataframe containing one or more polygon areas to be gridded
    length = number. length of desired grid square, in the units used by the targets' CRS. (i.e. meters)
    width = number. same as above.
    '''
    print(str(datetime.now().time())+" gridify() started")
    
    # Dissolves ROI into one single-part feature, in case of multi-polygons
    roi = roi.dissolve()

    print("Coordinate system of ROI:")
    print(roi.crs)
    print('Linear unit: '+roi.crs.axis_info[0].unit_name)
    mastergrid = gpd.GeoDataFrame(geometry = None)
    
    print('Creating grid length='+str(length)+' width='+str(width))
    for target in roi.geometry: # If only one polygon ROI is provided to the function that's fine, this loop will run once
        xmin, ymin, xmax, ymax = target.bounds
        cols = list(np.arange(xmin, xmax + width, width))
        rows = list(np.arange(ymin, ymax + length, length))
        # Create empty list to contain polygon grid squares
        polygons = [] 
        for x in cols[:-1]:
            for y in rows[:-1]:
                polygons.append(Polygon([(x,y), (x+width, y), (x+width, y+length), (x, y+length)]))
        # Convert list of poly geometries to a geodataframe
        grid = gpd.GeoDataFrame({'geometry':polygons})
        mastergrid = mastergrid.append(grid)
    
    # Specify CRS of grid (same as input ROI)
    mastergrid = mastergrid.set_crs(str(roi.crs))
    print("Coordinate system of grid squares:")
    print(str(mastergrid.crs))
    print('Linear unit: '+mastergrid.crs.axis_info[0].unit_name)
    
    if clip2shape==True:
        print("Clipping fishnet to ROI extents...")
        mastergrid = gpd.clip(mastergrid, roi)
        # Reset gridsquare index if clipping occurs
        mastergrid = mastergrid.reset_index(drop=True)
        
        
    print(str(datetime.now().time())+" gridify() finished!")
    return mastergrid


def grid_summarize(points, gridsquares, columndict=None):
    '''
    Returns a geodataframe with summarized attributes
    
    ARGUMENTS:
    points = point geodataframe
    columndict = a dictionary of each column you wish to summarize, 
        and the aggregating function you wish to use. 
        Possible values include 'sum', 'min', 'max', 'mean'
    gridsquares = polygon geodataframe, output of gridify()
    '''
    print(str(datetime.now().time())+" grid_summarize() started")
    
    # Spatial join points to empty gridsquares based on intersection
    # Returns df where rows = points within a gridsquare
    pointsinsquares = gpd.sjoin(gridsquares, points, how='inner', lsuffix='polys', rsuffix='points') 
    # reset_index() to make the 'index' of each gridsquare a column
    pointsinsquares = pointsinsquares.rename_axis('grid_index').reset_index(drop=False)
    # Create field with 1 as constant value, to be summed 
    pointsinsquares['pointcount'] = 1
    
    # create dictionary for aggregation functions
    aggdict = {'pointcount':'sum'}
    # Append any other aggregation functions specified by the user
    if columndict:
        aggdict.update(columndict)
    
    # Summarize the stats within each grid square
    gridsquaretotals = pointsinsquares.groupby(['grid_index']).agg(aggdict)
    gridsquaretotals = gridsquaretotals.reset_index()
    
    # Join the tabular stats to their gridsquare geometries
    output = gridsquares.merge(gridsquaretotals, left_index=True, right_on='grid_index', how='outer')
    # Fix the 'nan' indexes of gridsquares without datapoints
    output = output.reset_index(drop=True)
    # Fill all NA values in pointcount column with '0'
    output['pointcount'] = output['pointcount'].fillna(0)

    output = gpd.GeoDataFrame(output, geometry='geometry', crs=gridsquares.crs)
    print(str(datetime.now().time())+" grid_summarize() finished!")
    return output

def str_mode(x):
    '''
    Return the most frequently appearing string value in a series of strings
    (i.e., returning the "mode" of a string column)
    
    Parameters
    ----------
    x : a series or a column in a dataframe; must be of string type

    '''
    if len(x.value_counts()) == 0:
        return None
    else:
        return x.value_counts().index[0]
    
    
    
def merge_grid_summarize(basingrid, basingrid_ogim_points, basingrid_enverus_points):
    '''
    Parameters
    ----------
    basingrid : TYPE
        DESCRIPTION.
    basingrid_ogim_points : TYPE
        DESCRIPTION.
    basingrid_enverus_points : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    '''
    if not 'grid_index' in basingrid.columns:
        basingrid = basingrid.rename_axis('grid_index').reset_index(drop=False)
    else:
        pass
    # change identical column names prior to merge
    basingrid_ogim_points = basingrid_ogim_points.rename(columns={'pointcount':'count_ogim'})
    basingrid_enverus_points = basingrid_enverus_points.rename(columns={'pointcount':'count_enverus'})

    # Join Enverus stat columns to OGIM stat columns, using grid square index as merge field
    dfmerge = pd.merge(basingrid_ogim_points, basingrid_enverus_points, on='grid_index', how='outer')
    # merge point statistics columns to set of all basingrid cells; drop duplicate/uneeded geometry columns
    dfmerge_togrid = pd.merge(basingrid, dfmerge, on='grid_index', how='outer').drop(columns=['geometry_x','geometry_y'])
    # Convert intermediate df back into a gdf, 'reinstating' the geometry column
    output = gpd.GeoDataFrame(dfmerge_togrid, geometry='geometry', crs=basingrid.crs)
    # Drop any grid cells where NO points from either dataset appear in the grid square
    output = output.dropna(subset=['count_ogim','count_enverus'], how='all')
    # for Count fields, replace remaining nans with zeroes, to aid counting later on
    output.count_ogim = output.count_ogim.fillna(0)
    output.count_enverus = output.count_enverus.fillna(0)
    return output


def percentage_dif(ogim_col,enverus_col):
    '''
    Calculate the percentage difference across two numeric columns OR values, 
    while avoiding any "divide by zero" errors.
    '''
    if ogim_col == enverus_col:
        return 0
    if (enverus_col == 0) & (ogim_col !=0):
        return 999
    if (enverus_col != 0) & (ogim_col ==0):
        return -999
    try:
        return (((ogim_col - enverus_col) / ((ogim_col + enverus_col)/2)) * 100)
    except ZeroDivisionError:
        return float('inf')
