# =================================================================
#
# Copyright (c) 2025 Gecosistema S.r.l.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# =================================================================

import os
import json

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from ..cli.module_log import Logger, set_log_debug
from ..utils import filesystem
from ..utils.status_exception import StatusException

from .xbeach_retriever import _XBeachRetriever


PROCESS_METADATA = {
    'version': '0.2.0',
    'id': 'xbeach_retriever_process',
    'title': {
        'en': 'XBeach Data Retriever Process',
    },
    'description': {
        'en': 'Collect XBeach runup output data and return time series for the requested location and time range.',
    },
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'keywords': ['XBeach', 'runup', 'retriever', 'process', 'pygeoapi'],

    'inputs': {
        'token': {
            'title': 'secret token',
            'description': 'identify yourself',
            'schema': {
                'type': 'string'
            }
        },
        'lat_range': {
            'title': 'Latitude range',
            'description': 'The latitude range in format [lat_min, lat_max]. Values must be in EPSG:4326 crs. If no latitude range is provided, all latitudes will be returned',
            'schema': {}
        },
        'long_range': {
            'title': 'Longitude range',
            'description': 'The longitude range in format [long_min, long_max]. Values must be in EPSG:4326 crs. If no longitude range is provided, all longitudes will be returned',
            'schema': {}
        },
        'site_ids': {
            'title': 'Site IDs',
            'description': 'The site IDs to be used for the request. If no site IDs are provided, all sites will be returned',
            'schema': {}
        },
        'time_range': {
            'title': 'Time range',
            'description': 'The time range in format [time_start, time_end]. Both must be in ISO-Format and related to at least one week ago.',
            'schema': {}
        },
        'strict_time_range': {
            'title': 'Strict time range',
            'description': 'Enable strict time range to check data avaliability until requested end time. Default is false',
            'schema': {}
        },
        'out': {
            'title': 'Output file path',
            'description': 'The output file path for the retrieved data.',
            'schema': {
                'type': 'string'
            }
        },
        'out_format': {
            'title': 'Return format type',
            'description': 'The return format type. Possible values are "geojson", "dataframe".',
            'schema': {}
        },
        'bucket_destination': {
            'title': 'Bucket destination',
            'description': 'The bucket destination where the data will be stored. If not provided, the data will not be stored in a bucket.',
            'schema': {
                'type': 'string'
            }
        },
        'debug': {
            'title': 'Debug',
            'description': 'Enable Debug mode. Can be valued as true or false',
            'schema': {}
        }
    },

    'outputs': {
        'status': {
            'title': 'status',
            'description': 'Status of the process execution [OK or KO]',
            'schema': {}
        },
        's3_uri': {
            'title': 'S3 Uri',
            'description': 'S3 Uri of the stored feature collection',
            'schema': {}
        },
        'data': {
            'title': 'Time series dataset',
            'description': 'Dataset with runup forecast data time series in requested "out_format"',
            'schema': {}
        }
    },

    'example': {
        "inputs": {
            "debug": True,
            "token": "your_secret_token",
            "lat_range": [44, 44.5],
            "long_range": [12.2, 12.8],
            "time_range": ["2025-01-21T08:00:00.000", "2025-01-22T23:10:00.000"],
            "out_format": "geojson"
        }
    }
}


class XBeachRetrieverProcessor(BaseProcessor):
    """
    XBeach Data Retriever Process Processor
    """

    def __init__(self, processor_def):
        """
        Initialize the XBeach Retriever Processor.
        """

        super().__init__(processor_def, PROCESS_METADATA)

        self.name = 'XBeachRetrieverProcessor'

        self._tmp_data_folder = os.path.join(os.getcwd(), f'{self.name}_tmp')
        if not os.path.exists(self._tmp_data_folder):
            os.makedirs(self._tmp_data_folder)

        # Dual-mode configuration
        self.processor_mode = os.getenv('XBEACH_PROCESSOR_MODE', 'local').lower()
        if self.processor_mode not in ['local', 'lambda']:
            self.processor_mode = 'local'
        Logger.debug(f'XBeach Processor mode: {self.processor_mode}')

        # Lambda configuration (only loaded if mode is lambda)
        self._lambda_client = None
        self._lambda_function_name = None
        self._lambda_region = None
        if self.processor_mode == 'lambda':
            self._lambda_function_name = os.getenv('XBEACH_RETRIEVER_LAMBDA_FUNCTION_NAME')
            self._lambda_region = os.getenv('AWS_REGION', 'us-east-1')
            if not self._lambda_function_name:
                raise StatusException(
                    StatusException.INVALID,
                    'XBEACH_RETRIEVER_LAMBDA_FUNCTION_NAME environment variable is required when XBEACH_PROCESSOR_MODE=lambda'
                )


    def argument_validation(self, data):
        """
        Validate the arguments passed to the processor.
        """

        token = data.get('token', None)
        debug = data.get('debug', False)

        if token is None or token != os.getenv("INT_API_TOKEN", "token"):
            raise StatusException(StatusException.DENIED, 'ACCESS DENIED: wrong token')

        if type(debug) is not bool:
            raise StatusException(StatusException.INVALID, 'debug must be a boolean')
        if debug:
            set_log_debug()


    def _get_lambda_client(self):
        """
        Get or create boto3 Lambda client (lazy initialization).
        """
        if self._lambda_client is None:
            try:
                import boto3
            except ImportError:
                raise StatusException(
                    StatusException.ERROR,
                    'boto3 is required for Lambda mode. Install it with: pip install boto3'
                )
            self._lambda_client = boto3.client('lambda', region_name=self._lambda_region)
        return self._lambda_client


    def _invoke_lambda(self, data):
        """
        Invoke Lambda function synchronously and return normalized response.
        """
        client = self._get_lambda_client()

        try:
            payload = json.dumps(data)
            Logger.debug(f'Invoking Lambda function: {self._lambda_function_name}')

            response = client.invoke(
                FunctionName=self._lambda_function_name,
                InvocationType='RequestResponse',
                Payload=payload
            )

            if response['StatusCode'] != 200:
                raise StatusException(
                    StatusException.ERROR,
                    f'Lambda returned status code {response["StatusCode"]}'
                )

            result_payload = json.load(response['Payload'])
            Logger.debug(f'Lambda response: {result_payload}')

            if isinstance(result_payload, dict):
                if 'body' in result_payload and isinstance(result_payload['body'], dict):
                    return result_payload['body'].get('result', result_payload)
                elif 'result' in result_payload:
                    return result_payload['result']
                else:
                    return result_payload
            else:
                return result_payload

        except Exception as err:
            if isinstance(err, StatusException):
                raise
            raise StatusException(
                StatusException.ERROR,
                f'Lambda invocation failed: {str(err)}'
            )


    def execute(self, data):

        mimetype = 'application/json'
        outputs = {}
        cleanup_needed = False

        try:

            # DOC: Args validation
            self.argument_validation(data)
            Logger.debug('Validated process parameters')

            # DOC: Execute based on processor mode
            if self.processor_mode == 'lambda':
                Logger.debug('Executing in Lambda mode')
                outputs = self._invoke_lambda(data)
            else:
                Logger.debug('Executing in local mode')
                cleanup_needed = True
                XBeachRetriever = _XBeachRetriever()
                outputs = XBeachRetriever.run(**data)

        except StatusException as err:
            outputs = {
                'status': err.status,
                'message': str(err)
            }
        except Exception as err:
            outputs = {
                'status': StatusException.ERROR,
                'error': str(err)
            }
            raise ProcessorExecuteError(str(err))
        finally:
            if cleanup_needed:
                filesystem.garbage_folders(self._tmp_data_folder)
                Logger.debug(f'Cleaned up temporary data folder: {self._tmp_data_folder}')

        return mimetype, outputs


    def __repr__(self):
        return f'<XBeachRetrieverProcessor> {self.name}'
