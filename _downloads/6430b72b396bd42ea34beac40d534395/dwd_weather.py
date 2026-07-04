import pandas as pd
import numpy as np
import geopandas as gpd
from datetime import datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
import seaborn as sns
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from tqdm import tqdm
from PIL import Image
from functools import lru_cache

@lru_cache(maxsize=3)
def load_borders(filename="germany_federal_states.geojson"):
    # Load once, outside the loop
    borders = gpd.read_file(filename)
    
    # Make sure borders use longitude/latitude coordinates
    if borders.crs is not None:
        borders = borders.to_crs("EPSG:4326")
    return borders

def load_index(path:str):
    import os

    # Find the first .txt file in the specified path
    txt_file = next(f for f in os.listdir(path) if f.endswith('.txt'))

    # Load the fixed-width formatted text file into a pandas DataFrame with latin1 encoding
    colspecs = [
        (0, 5),    # Stations_id
        (5, 15),   # von_datum
        (15, 24),   # bis_datum
        (24, 39),   # Stationshoehe
        (39, 51),   # geoBreite
        (51, 61),   # geoLaenge
        (61, 102),  # Stationsname
        (102, 143), # Bundesland
        (143, None) # Abgabe
    ]

    df = pd.read_fwf(
        f"{path}/{txt_file}",
        colspecs=colspecs,
        skiprows=2,
        names=[
            "Stations_id",
            "von_datum",
            "bis_datum",
            "Stationshoehe",
            "geoBreite",
            "geoLaenge",
            "Stationsname",
            "Bundesland",
            "Abgabe",
        ],
        dtype={"Stations_id": str},
        encoding='latin1'
    )

    return df

def load_station(path:str, station_name:str):

    import zipfile

    import os

    # Find the first .zip file containing station_name in the filename
    try:
        zip_file_name = next(f for f in os.listdir(path) if f.endswith('.zip') and station_name in f)
    except:
        #print(f"searching for {station_name} in {path} failed")
        return None
        
    zip_file_path = f"{path}/{zip_file_name}"

    # Extract the .txt file from the zip archive
    with zipfile.ZipFile(zip_file_path, 'r') as z:

        # Extract all contents
        z.extractall()

        # Identify the .txt file inside the zip
        txt_file_name = z.namelist()[0]

    # Load the .txt file as a semicolon-separated pandas DataFrame
    df = pd.read_csv(txt_file_name, sep=';')

    # delete the text file again after reading
    os.remove(txt_file_name)

    # Display the first few rows
    return df


def load_timeseries(station_ids, path, column):
    from datetime import datetime
    import pandas as pd
    from tqdm import tqdm
    
    # Initialize a list to collect data from all stations
    all_station_data = []
    
    # Iterate through each station ID
    for station_id in tqdm(station_ids):
        #try:
            # Load time-series data for the station
            station_data = load_station(path, station_id)
            if station_data is None:
                continue
            
            # Extract the relevant columns
            relevant_data = station_data #[['MESS_DATUM', column]]
            relevant_data['Stations_id'] = station_id
            
            # Append to the list
            all_station_data.append(relevant_data)
        #except:
        #    print("Error loading", station_id)
        #    pass
    
    # Combine all data into a single DataFrame
    combined_df = pd.concat(all_station_data, ignore_index=True)
    # -999 seems to be a code for NaN
    #combined_df["Wert"] = combined_df[column].replace(-999.0, np.nan)

    return combined_df #[["MESS_DATUM", "Station_id", "Wert"]]



def generate_plot_stack(
    df,
    column_to_plot,
    min_value=-40,
    max_value=40,
    colormap="coolwarm",
    borders_gdf=None,
    step=6
):
    # Filter timepoints for the selected date range
    time_points = sorted(df["datetime"].unique())

    frames = []

    # fixed legend
    steps = 5
    fixed_temps = [
        round(min_value + i * (max_value - min_value) / (steps - 1), 1)
        for i in range(steps)
    ]
    norm = Normalize(vmin=min_value, vmax=max_value)
    cmap = plt.colormaps[colormap]
    legend_handles = [
        mpatches.Patch(color=cmap(norm(t)), label=str(t))
        for t in fixed_temps
    ]

    for selected_time_point in tqdm(time_points[::step]):

        # Filter data for the selected time-point
        filtered_data = df[df["datetime"] == selected_time_point]

        # Skip timepoints where hardly any data is available
        if filtered_data.shape[0] < 20:
            continue

        # Plot
        fig, ax = plt.subplots(figsize=(5, 6))

        # Add German federal state borders
        borders_gdf.boundary.plot(
            ax=ax,
            color="black",
            linewidth=0.6,
            alpha=0.8,
            zorder=1
        )

        # Add measurement points
        scatter = sns.scatterplot(
            data=filtered_data,
            x="geoLaenge",
            y="geoBreite",
            hue=column_to_plot,
            palette=colormap,
            ax=ax,
            hue_norm=(min_value, max_value),
            s=45,
            edgecolor="black",
            linewidth=0.2,
            zorder=2
        )

        ax.set_title(f"{column_to_plot} at Time-point {selected_time_point}")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

        # Fixed Germany map extent
        #ax.set_xlim(5.5, 15.5)
        #ax.set_ylim(47.0, 55.5)
        #ax.set_aspect("equal", adjustable="box")

        # Remove auto legend and add fixed legend
        if ax.get_legend() is not None:
            ax.get_legend().remove()
        ax.legend(handles=legend_handles, title=column_to_plot, loc="lower right", bbox_to_anchor=(1, 0),)

        # Convert plot to numpy array using BytesIO
        buf = BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        plot_array = plt.imread(buf)
        plot_array = (plot_array[..., :3] * 255).astype(np.uint8)
        plt.close(fig)

        target_shape = (600, 500, 3)
        target_h, target_w, _ = target_shape
        if plot_array.shape != target_shape:
            img = Image.fromarray(plot_array)
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            plot_array = np.asarray(img, dtype=np.uint8)  
        frames.append(plot_array)  

    shapes = {arr.shape for arr in frames}
    if len(shapes) != 1:
        print(shapes)
        
    
    return np.stack(frames, axis=0)  # Shape: (T, Y, X, C)