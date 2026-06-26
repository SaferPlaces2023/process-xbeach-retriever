import os
import json
import array
import datetime

import numpy as np
import pandas as pd

import geopandas as gpd

from ..cli.module_log import Logger
from ..utils import filesystem, module_s3, module_ftp
from ..utils.status_exception import StatusException
from ..utils.filesystem import tempdir


class _XBeachRetriever():
    """
    Class to retrieve XBeach runup data for a given time range and location
    bounds. Data is downloaded from the ARPAE FTPS server as binary rugau .dat
    files and parsed into per-site time series.
    """

    name = 'XBeachRetrieverProcessor'

    dataset_name = 'XBEACH'
    variable_name = 'runup'

    # DOC: ugly asf but this is the ftp data source
    avaliable_sites = {
        'rimini-01': dict(ftp_filename='rugau_rimini01.dat'),
        'riccione-01': dict(ftp_filename='rugau_riccio01.dat'),
        'riccione-02': dict(ftp_filename='rugau_riccio02.dat'),
    }

    # if XBEACH_PROCESSOR_MODE use tempdir else use current working directory
    _tmp_data_folder = tempdir(f'{name}_tmp') if os.getenv('XBEACH_PROCESSOR_MODE') == "lambda" else os.path.join(os.getcwd(), f'{name}_tmp')

    def __init__(self):
        if not os.path.exists(self._tmp_data_folder):
            os.makedirs(self._tmp_data_folder)


    # REGION: [ Argument validation ] ----------------------------------------

    def argument_validation(self, **kwargs):
        """
        Validate the arguments passed to the retriever.
        """

        lat_range = kwargs.get('lat_range', None)
        long_range = kwargs.get('long_range', None)
        site_ids = kwargs.get('site_ids', None)
        time_range = kwargs.get('time_range', None)
        time_start = time_range[0] if type(time_range) in [list, tuple] else time_range
        time_end = time_range[1] if type(time_range) in [list, tuple] else None
        strict_time_range = kwargs.get('strict_time_range', False)
        out_format = kwargs.get('out_format', None)
        bucket_destination = kwargs.get('bucket_destination', None)
        out = kwargs.get('out', None)

        if lat_range is not None:
            if type(lat_range) is not list or len(lat_range) != 2:
                raise StatusException(StatusException.INVALID, 'lat_range must be a list of 2 elements')
            if type(lat_range[0]) not in [int, float] or type(lat_range[1]) not in [int, float]:
                raise StatusException(StatusException.INVALID, 'lat_range elements must be float')
            if lat_range[0] < -90 or lat_range[0] > 90 or lat_range[1] < -90 or lat_range[1] > 90:
                raise StatusException(StatusException.INVALID, 'lat_range elements must be in the range [-90, 90]')
            if lat_range[0] > lat_range[1]:
                raise StatusException(StatusException.INVALID, 'lat_range[0] must be less than lat_range[1]')
        else:
            lat_range = [-90, 90]

        if long_range is not None:
            if type(long_range) is not list or len(long_range) != 2:
                raise StatusException(StatusException.INVALID, 'long_range must be a list of 2 elements')
            if type(long_range[0]) not in [int, float] or type(long_range[1]) not in [int, float]:
                raise StatusException(StatusException.INVALID, 'long_range elements must be float')
            if long_range[0] < -180 or long_range[0] > 180 or long_range[1] < -180 or long_range[1] > 180:
                raise StatusException(StatusException.INVALID, 'long_range elements must be in the range [-180, 180]')
            if long_range[0] > long_range[1]:
                raise StatusException(StatusException.INVALID, 'long_range[0] must be less than long_range[1]')
        else:
            long_range = [-180, 180]

        if site_ids is not None:
            if type(site_ids) is not list:
                raise StatusException(StatusException.INVALID, 'site_ids must be a list of site IDs')
            if any(not isinstance(site_id, str) for site_id in site_ids):
                raise StatusException(StatusException.INVALID, 'site_ids must be a list of strings')
            if any(site_id not in self.avaliable_sites for site_id in site_ids):
                raise StatusException(StatusException.INVALID, f'site_ids must be in {list(self.avaliable_sites.keys())}')
        else:
            site_ids = list(self.avaliable_sites.keys())
        if len(site_ids) == 0:
            site_ids = list(self.avaliable_sites.keys())

        if time_start is None:
            raise StatusException(StatusException.INVALID, 'Cannot process without a time valued')
        if type(time_start) is not str:
            raise StatusException(StatusException.INVALID, 'time_start must be a string')
        try:
            time_start = datetime.datetime.fromisoformat(time_start)
        except ValueError:
            raise StatusException(StatusException.INVALID, 'time_start must be a valid datetime iso-format string')

        if time_end is not None:
            if type(time_end) is not str:
                raise StatusException(StatusException.INVALID, 'time_end must be a string')
            try:
                time_end = datetime.datetime.fromisoformat(time_end)
            except ValueError:
                raise StatusException(StatusException.INVALID, 'time_end must be a valid datetime iso-format string')
            if time_start > time_end:
                raise StatusException(StatusException.INVALID, 'time_start must be less than time_end')

        # DOC: round to 15 minutes
        time_start = time_start.replace(minute=(time_start.minute // 15) * 15, second=0, microsecond=0)
        time_end = time_end.replace(minute=(time_end.minute // 15) * 15, second=0, microsecond=0) if time_end is not None else time_start + datetime.timedelta(hours=1)
        if time_start == time_end:
            time_end = time_start + datetime.timedelta(hours=1)

        if strict_time_range is not None:
            if type(strict_time_range) is not bool:
                raise StatusException(StatusException.INVALID, 'strict_time_range must be a boolean')

        if out_format is not None:
            if type(out_format) is not str:
                raise StatusException(StatusException.INVALID, 'out_format must be a string or null')
            if out_format not in ['geojson', 'dataframe']:
                raise StatusException(StatusException.INVALID, 'out_format must be one of ["geojson", "dataframe"]')

        if bucket_destination is not None:
            if type(bucket_destination) is not str:
                raise StatusException(StatusException.INVALID, 'bucket_destination must be a string')
            if not bucket_destination.startswith('s3://'):
                raise StatusException(StatusException.INVALID, 'bucket_destination must start with "s3://"')

        if out is not None:
            if type(out) is not str:
                raise StatusException(StatusException.INVALID, 'out must be a string')
            dirname, _ = os.path.split(out)
            if dirname != '' and not os.path.exists(dirname):
                os.makedirs(dirname)

        return {
            'lat_range': lat_range,
            'long_range': long_range,
            'site_ids': site_ids,
            'time_start': time_start,
            'time_end': time_end,
            'strict_time_range': strict_time_range,
            'out_format': out_format,
            'bucket_destination': bucket_destination,
            'out': out,
        }


    # REGION: [ Binary .dat parsing ] ----------------------------------------

    def _readdims(self, fullfile):
        """read dimensions from dims.dat"""
        with open(fullfile, mode='rb') as fileobj:
            binvalues = array.array('d')
            binvalues.fromfile(fileobj, 1 * 14)
            dims = np.array(binvalues, dtype=int)
            nt, nx, ny = tuple(1 + dims[0:3])
        return nt, nx, ny

    def _readxy(self, fullfile, nx, ny):
        """read x and y from xy.dat"""
        with open(fullfile, mode='rb') as fileobj:
            binvalues = array.array('d')
            binvalues.fromfile(fileobj, nx * ny * 3)
        xy = np.array(binvalues)
        x = np.reshape(xy[0:nx * ny], (ny, nx)).T
        y = np.reshape(xy[nx * ny:-nx * ny], (ny, nx)).T
        x_xb = np.reshape(xy[-nx * ny:], (ny, nx)).T
        return x, y, x_xb

    def _rugau_to_gdf(self, rugau_path, dims_path=None, xy_path=None, init_datetime=None, target_epsg=None):
        dims_path = os.path.join(os.path.dirname(rugau_path), 'dims.dat') if dims_path is None else dims_path
        xy_path = os.path.join(os.path.dirname(rugau_path), 'xy.dat') if xy_path is None else xy_path

        nt = None
        if isinstance(xy_path, str) and os.path.exists(xy_path):
            nt, nx, ny = self._readdims(dims_path)
            xg, yg, xg_xb = self._readxy(xy_path, nx, ny)
        if isinstance(dims_path, str) and os.path.exists(dims_path):
            dims_all = np.fromfile(dims_path, dtype=np.float64)
            tsglobal = dims_all[10:10 + (nt - 1)]
            ntimes = len(tsglobal)
        else:
            ntimes = 337

        rugau = np.fromfile(rugau_path, dtype=np.float64).reshape(ntimes, 4)
        t, x, y, v = rugau.T

        df = pd.DataFrame({'seconds': t, 'lon': x, 'lat': y, self.variable_name: v})
        if init_datetime is not None:
            df['date_time'] = pd.to_datetime(init_datetime) + pd.to_timedelta(df['seconds'], unit='s')
            del df['seconds']
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs='EPSG:32632')
        del gdf['lon']
        del gdf['lat']
        if target_epsg is not None and gdf.crs.to_epsg() != target_epsg:
            gdf = gdf.to_crs(epsg=target_epsg)

        return gdf


    # REGION: [ Data retrieval ] ---------------------------------------------

    def retrieve_data(self, long_range, lat_range, time_start, time_end, site_ids=None):
        """
        Retrieve XBeach runup data for the given time range and location bounds.
        """
        Logger.debug(f'XBEACH - Retrieving data for lat_range: {lat_range}, long_range: {long_range}, time_start: {time_start}, time_end: {time_end}, site_ids: {site_ids}')

        # DOC: List of requested dates
        requested_dates = pd.date_range(start=time_start.date(), end=time_end.date(), freq='D').to_pydatetime().tolist()

        # DOC: Connect to the FTP server (lazily)
        ftps = None

        def get_date_dataset_local_path(rd):
            return os.path.join(self._tmp_data_folder, f'{self.dataset_name}__{rd.isoformat()}.geojson')

        date_dataset_local_paths = {
            rd: get_date_dataset_local_path(rd.date())
            for rd in requested_dates
        }

        try:
            for requested_date, filepath in date_dataset_local_paths.items():

                if filepath is not None and os.path.exists(filepath):
                    Logger.debug(f'XB - Dataset {requested_date} already present locally, skipping download')
                    continue

                # DOC: Connect to the FTP server if not already connected
                if ftps is None:
                    ftps = module_ftp.ftp_connect(
                        host=os.environ['FTPS_ARPAE_HOST'],
                        user=os.environ['FTPS_ARPAE_USERNAME'],
                        password=os.environ['FTPS_ARPAE_PASSWORD']
                    )

                # DOC: Gather and build from FTP
                ftp_date_filepaths = {
                    site_id: os.path.join(requested_date.strftime('%Y%m%d'), site_specs['ftp_filename'])
                    for site_id, site_specs in self.avaliable_sites.items()
                    if site_id in site_ids
                }
                ftp_date_filepath_exist = [module_ftp.ftp_exists_path_mlsd(ftps, ftp_date_filepath) for ftp_date_filepath in ftp_date_filepaths.values()]
                if not all(ftp_date_filepath_exist):
                    raise StatusException(StatusException.SKIPPED, f'XB - Not all files for date {requested_date} are available in FTP server: {ftp_date_filepaths}')

                date_filepaths = dict()
                for site_id, ftp_date_filepath in ftp_date_filepaths.items():
                    fp = module_ftp.ftp_download(ftps, ftp_date_filepath, local_dir=os.path.join(self._tmp_data_folder, requested_date.isoformat()))
                    date_filepaths[site_id] = fp
                if not all(os.path.exists(fp) for fp in date_filepaths.values()):
                    raise StatusException(StatusException.ERROR, f'XB - Not all files for date {requested_date} were downloaded successfully: {date_filepaths}')

                # DOC: Combine all files into a single GeoDataFrame related to the requested date
                dataframes = []
                for sid, dp in date_filepaths.items():
                    sgdf = self._rugau_to_gdf(dp, dims_path=False, xy_path=False, init_datetime=requested_date, target_epsg=4326)
                    sgdf['site'] = sid
                    dataframes.append(sgdf)
                gdf = pd.concat(dataframes, ignore_index=True).reset_index(drop=True)
                gdf = gdf[gdf.date_time.dt.date == requested_date.date()].copy()

                # DOC: Save the dataset locally
                gdf.to_file(filepath, driver='GeoJSON')

        finally:
            # DOC: Close the FTP connection
            if ftps is not None:
                module_ftp.ftp_close(ftps)

        Logger.debug(f"XB - Requested date - dataset paths: {date_dataset_local_paths}")

        # DOC: For each site, for each requested date, retrieve the data
        site_gdfs = dict()
        for rd, fp in date_dataset_local_paths.items():
            if not os.path.exists(fp):
                continue
            gdf_date = gpd.read_file(fp)
            gdf_date['date_time'] = pd.to_datetime(gdf_date['date_time'])
            gdf_date = gdf_date[(gdf_date.date_time >= time_start) & (gdf_date.date_time <= time_end)].reset_index(drop=True)
            for sid in site_ids:
                gdf_site = gdf_date.copy()[gdf_date['site'] == sid].reset_index(drop=True)
                gdf_site = gdf_site.cx[long_range[0]:long_range[1], lat_range[0]:lat_range[1]]
                if gdf_site.empty:
                    Logger.warning(f'XB - Site {sid} is outside the requested range {lat_range}, {long_range}. Skipping.')
                    continue

                site_gdfs[sid] = gdf_site if sid not in site_gdfs else pd.concat([site_gdfs[sid], gdf_site]).drop_duplicates(subset=['date_time'], keep='last').reset_index(drop=True)
                site_gdfs[sid] = site_gdfs[sid].sort_values(by='date_time').reset_index(drop=True)

        if len(site_gdfs) == 0:
            return site_gdfs

        # DOC: ensure all sites have same dimensions
        max_length = max(len(df) for df in site_gdfs.values())
        if any(len(df) != max_length for df in site_gdfs.values()):
            raise StatusException(StatusException.ERROR, 'XB - Not all sites have the same number of time steps. Please check the data availability for the requested time range.')

        return site_gdfs


    # REGION: [ Output formatting ] ------------------------------------------

    def site_dfs_2_feature_collection(self, site_dfs):
        """
        Convert site dataframes to a GeoJSON feature collection. Each feature is
        a site whose `runup` property is a list of [date_time, value] pairs.
        """

        features = []
        for sid, df in site_dfs.items():
            df['date_time'] = df['date_time'].apply(lambda x: x.isoformat() if isinstance(x, (datetime.datetime, pd.Timestamp)) else x)
            site_feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [df.iloc[0].geometry.x, df.iloc[0].geometry.y],
                },
                'properties': {
                    'site_id': sid,
                    'date_time': df.iloc[0]['date_time'],
                    self.variable_name: [[row['date_time'], row[self.variable_name]] for _, row in df.sort_values(by='date_time').iterrows()]
                }
            }
            features.append(site_feature)

        feature_collection = {
            'type': 'FeatureCollection',
            'features': features,
            "metadata": {
                "field": [
                    {
                        "@name": self.variable_name,
                        "@alias": self.variable_name,
                        "@unit": "m",
                        "@type": "elevation"
                    }
                ]
            },
            "crs": {
                "type": "name",
                "properties": {
                    "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
                }
            }
        }

        time_value = feature_collection['features'][0]['properties']['date_time']
        timestamp_geojson_filename = filesystem.normpath(f'{self.dataset_name}__{self.variable_name}__{time_value}.geojson')
        timestamp_geojson_filepath = os.path.join(self._tmp_data_folder, timestamp_geojson_filename)
        with open(timestamp_geojson_filepath, 'w') as f:
            json.dump(feature_collection, f, indent=4)

        return feature_collection, timestamp_geojson_filepath


    # REGION: [ Run ] --------------------------------------------------------

    def run(
        self,
        lat_range=None,
        long_range=None,
        site_ids=None,
        time_range=None,
        strict_time_range=False,
        out_format=None,
        bucket_destination=None,
        out=None,
        **kwargs
    ):
        """
        Run the XBeach Retriever.
        """

        try:

            # DOC: Validate the arguments
            validated_args = self.argument_validation(
                lat_range=lat_range,
                long_range=long_range,
                site_ids=site_ids,
                time_range=time_range,
                strict_time_range=strict_time_range,
                out_format=out_format,
                bucket_destination=bucket_destination,
                out=out,
            )
            lat_range = validated_args['lat_range']
            long_range = validated_args['long_range']
            site_ids = validated_args['site_ids']
            time_start = validated_args['time_start']
            time_end = validated_args['time_end']
            out_format = validated_args['out_format']
            bucket_destination = validated_args['bucket_destination']
            out = validated_args['out']
            Logger.debug(f"Running XBeach Retriever with parameters: {validated_args}")

            # DOC: Retrieve data from the XBeach model
            sites_dataframes = self.retrieve_data(long_range, lat_range, time_start, time_end, site_ids)
            if len(sites_dataframes) == 0:
                raise StatusException(StatusException.SKIPPED, 'No data available for the requested range')

            # DOC: Each site dataframes becomes a GeoJSON feature collection
            feature_collection, timestamp_geojson_filepath = self.site_dfs_2_feature_collection(sites_dataframes)

            # DOC: Upload to S3 if a bucket destination is provided
            timestamp_geojson_s3_uri = None
            if bucket_destination is not None:
                timestamp_geojson_s3_uri = f'{bucket_destination}/{os.path.basename(timestamp_geojson_filepath)}'
                upload_status = module_s3.s3_upload(timestamp_geojson_filepath, timestamp_geojson_s3_uri)
                if not upload_status:
                    raise StatusException(StatusException.ERROR, f"Failed to upload data to bucket {timestamp_geojson_s3_uri}")
                Logger.debug(f"Data stored in bucket: {timestamp_geojson_s3_uri}")

            # DOC: Format output data if requested
            out_data = dict()
            if out_format is not None:
                if out_format == 'dataframe':
                    out_dataset = {sid: df.drop(columns='geometry').to_dict(orient='records') for sid, df in sites_dataframes.items()}
                    out_data = {'data': out_dataset, 'out_format': 'dataframe'}
                else:
                    out_data = {'data': feature_collection, 'out_format': 'geojson'}
                if out is not None:
                    with open(out, 'w') as f:
                        json.dump(out_data['data'], f)
                    Logger.debug(f"Output written to {out}")

            # DOC: Prepare outputs
            outputs = {
                'status': 'OK',
                **({'s3_uri': timestamp_geojson_s3_uri} if timestamp_geojson_s3_uri is not None else {}),
                **({'filepath': out} if out is not None else {}),
                **out_data
            }
            Logger.debug("Outputs prepared")

            # DOC: Clean up temporary data folder
            filesystem.garbage_folders(self._tmp_data_folder)
            Logger.debug(f'Cleaned up temporary data folder: {self._tmp_data_folder}')

            return outputs

        except Exception as ex:
            filesystem.garbage_folders(self._tmp_data_folder)
            Logger.debug(f'Cleaned up temporary data folder: {self._tmp_data_folder} before raising exception')
            raise ex
