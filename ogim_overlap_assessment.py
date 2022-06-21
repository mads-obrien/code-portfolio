# -*- coding: utf-8 -*-
"""
Created on Fri Dec 10 15:09:41 2021

This workflow compares the spatial extents and point densities of two 
vector (point) datasets.
In the example below, two oil and gas well datasets in Argentina are compared.

Change the variable assignments in Cell #0 and Cell #1 (data import), 
then you should be able to click "run" and leave the script alone.

@author: maobrien
"""
import os
import pandas as pd
import geopandas as gpd
from datetime import datetime
import matplotlib.pyplot as plt

# import custom gridify functions
os.chdir('C:\\path\\to\\functions')
from gridify import *  # load custom functions

# Set current working directory
os.chdir("C:\\path\\to\\workingdirectory")


# Variables to define at start
basin_name = 'Neuquen'
infra_name = 'Wells'
epsgcode = 32719   # look up the UTM zone that best covers your basin of interest, and its EPSG code
lw_grid = 5000  # length and width in meters of desired grid squares


ExportWhenDone = True    # Switch to "turn on" the 'Export to shapefile' line at the end of this script
output_filepath = 'C:\\path\\scratch\\overlap_testing\\'


# =============================================================================
#%%Load in Data (may take a while with large datasets)
# =============================================================================
# load basin geometry
basin = gpd.read_file(r"raw_data\basins\Neuquen_Argentina_.shp")

# Load OGIM data
fp = 'C:\\path\\OGIM_NA_SA_v1b_.gpkg'
ogim_points = gpd.read_file(fp, layer='Wells')
print('OGIM points successfully loaded')
# To speed up processing time, filter to just the records in the countries or states covered by the basin geometry
ogim_points = ogim_points[ogim_points.COUNTRY=='Argentina']
# ## Situation with 2+ countries in a basin (i.e. Bakken basin covers, US and Canada)
# ogim_points = ogim_points[(ogim_points.COUNTRY == 'United States') | (ogim_points.COUNTRY == 'Canada')]


# list columns you want to keep in the very large Enverus spreadsheet
columnlist = ['Well ID','Country','Operator Int Name','Well Classification','Deviation Type','Technical Status','Content Status','Spud Date','Latitude (DD)','Longitude (DD)']
fp2 = 'C:\\path\\Proprietary_Data\\Enverus_Drillinginfo\\DI_int_Wells_CustomTable_.csv'
# read in enverus CSV using only specified columns
enverus_points_table = pd.read_csv(fp2, usecols=columnlist)
# OPTIONAL: filter records if desired to reduce GDF size)
enverus_points_table = enverus_points_table[enverus_points_table.Country=='Argentina']
print('Enverus point successfully loaded')

# Convert regular dataframe to GeoDataFrame
enverus_points = gpd.GeoDataFrame(enverus_points_table, geometry=gpd.points_from_xy(enverus_points_table['Longitude (DD)'], enverus_points_table['Latitude (DD)']), crs=4326)



# =============================================================================
#%% Reproject all into same coordinate system  
# =============================================================================
basin = basin.to_crs(epsg=epsgcode)

ogim_points = ogim_points.to_crs(epsg=epsgcode)
print(str(datetime.now().time())+' ogim_points reprojected')
enverus_points = enverus_points.to_crs(epsg=epsgcode)
print(str(datetime.now().time())+' enverus_points reprojected')

# Print count of total # of records in each dataset
print('ogim_points contains '+str(len(ogim_points))+' records')
print('enverus_points contains '+str(len(enverus_points))+' records')  



# =============================================================================
#%% Create empty grid covering basin of interest
# =============================================================================
basingrid = gridify(basin, length=lw_grid, width=lw_grid, clip2shape=False) 
basingrid.iloc[1:10].boundary.plot()  # quick plot of the first few grid squares to make sure that gridify() worked


# =============================================================================
#%% Tally # of public points and # of private points within each grid square
# =============================================================================
# Specify how the columns in your original point data will be summarized
columndict = {'SRC_URL' : lambda x:x.value_counts().index[0], 'FAC_STATUS' : lambda x:x.value_counts().index[0]} # take most common value in these columns
# Overlay your empty grid (basingrid) over the point data (ogim_points)
basingrid_ogim_points = grid_summarize(ogim_points, basingrid, columndict)
basingrid_ogim_points = basingrid_ogim_points.rename(columns={'SRC_URL':'SRC_URL_mode', 'FAC_STATUS':'FAC_STATUS_mode'})

# Repeat the process for the enverus data
columndict2 = {'Technical Status' : lambda x:x.value_counts().index[0]} # take most common source
basingrid_enverus_points = grid_summarize(enverus_points, basingrid, columndict2)
basingrid_enverus_points = basingrid_enverus_points.rename(columns={'Technical Status':'Status_mode'})


# =============================================================================
#%% Quick visualize grid squares by point count - Enverus
# =============================================================================
# Initialize a figure and axis
fig = plt.figure(1, figsize=(6,7)) 
ax = fig.add_subplot()

basingrid_enverus_points.plot(ax=ax, column='pointcount', cmap="plasma", legend=True)
ax.set_title("Enverus points in "+basin_name)
# ax.set_xlabel("easting", fontsize="small")
# ax.set_ylabel("northing", fontsize="small")

# =============================================================================
#%% Visualize grid squares by point count - OGIM
# =============================================================================
# Initialize a figure and axis
fig = plt.figure(1, figsize=(6,7)) 
ax = fig.add_subplot()

basingrid_ogim_points.plot(ax=ax, column='pointcount', cmap="afmhot", legend=True)
ax.set_title("OGIM points in "+basin_name)
# ax.set_xlabel("longitude", fontsize="small")
# ax.set_ylabel("latitude", fontsize="small")

# =============================================================================
#%% Merge the OGIM and Enverus grid square counts together, 
# into one single grid (using your original empty "basingrid" as a template)
# =============================================================================
basingrid_stats = merge_grid_summarize(basingrid, basingrid_ogim_points, basingrid_enverus_points)


# =============================================================================
#%% Calculate fields that compare OGIM and Enverus wells
# POSITIVE means more wells in OGIM within this gridsquare
# NEGATIVE means more wells in Enverus within this gridsquare
# =============================================================================

# Raw difference in point count within the grid square
basingrid_stats['count_diff'] = basingrid_stats.count_ogim - basingrid_stats.count_enverus

# Leave this function definition as-is
def percentage_dif(ogim_col,enverus_col):
    '''
    Calculate the percentage difference across two numeric columns OR values, 
    while avoiding any "divide by zero" errors.
    
    If a grid square only has one data source, it's meaningless to calculate a 
    "percentage difference" between x and 0. Instead, 
    fill the column with the code 999 or -999
    (positive = more OGIM, negative = more Enverus)
    
    '''
    if ogim_col == enverus_col:
        return 0
    if (enverus_col == 0) & (ogim_col !=0):  # if only 
        return 999
    if (enverus_col != 0) & (ogim_col ==0): 
        return -999
    try:
        return (((ogim_col - enverus_col) / ((ogim_col + enverus_col)/2)) * 100)
    except ZeroDivisionError:
        return float('inf')
     
basingrid_stats['pct_diff'] = basingrid_stats[['count_ogim','count_enverus']].apply(lambda x: percentage_dif(x['count_ogim'], x['count_enverus']), axis=1)


# =============================================================================
#%% Add categorical field that classifies a grid square as containing OGIM points only, ENVERUS points only, or Both
# =============================================================================
basingrid_stats['coverage'] = None

basingrid_stats.loc[(basingrid_stats.count_ogim != 0) & (basingrid_stats.count_enverus == 0),'coverage'] = 'OGIM only'
basingrid_stats.loc[(basingrid_stats.count_ogim == 0) & (basingrid_stats.count_enverus != 0),'coverage'] = 'Enverus only'
basingrid_stats.loc[(basingrid_stats.count_ogim != 0) & (basingrid_stats.count_enverus != 0),'coverage'] = 'Both'


#%%
if ExportWhenDone == True:
    num = str(int(lw_grid / 1000))
    outfilename = 'overlap_'+basin_name+'_'+num+'x'+num+'_'+infra_name
    basingrid_stats.to_file(output_filepath + outfilename+'.shp')
    print(str(datetime.now().time())+' successfully saved '+outfilename)    

print(str(datetime.now().time())+" Overlap Analysis Completed")

# NEXT STEP: generate plots from this output using 'OverlapAssessmentFIGURES.py'
