# -----------------------------------------------------------------------------
# License:
# Copyright (c) 2025 Gecosistema S.r.l.
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
#
# Name:        main.py
# Purpose:
#
# Author:      Luzzi Valerio
#
# Created:     18/03/2021
# -----------------------------------------------------------------------------
import click
import pprint
import traceback

from .cli.module_log import Logger
from .utils.status_exception import StatusException
from .utils.module_prologo import prologo, epilogo

from .xbeach import _XBeachRetriever


class _ARG_NAMES():
    LAT_RANGE = {
        'aliases': ['--lat_range', '--lat', '--latitude_range', '--latitude', '--lt'],
        'help': "Latitude range as two floats (min, max).",
        'default': None,
        'example': '--lat_range 44 44.5',
    }
    LONG_RANGE = {
        'aliases': ['--long_range', '--long', '--longitude_range', '--longitude', '--lg'],
        'help': "Longitude range as two floats (min, max).",
        'default': None,
        'example': '--long_range 12.2 12.8',
    }
    SITE_IDS = {
        'aliases': ['--site_ids', '--sites', '--sid'],
        'help': "Site IDs as a JSON list of strings (e.g. '[\"rimini-01\"]').",
        'default': None,
        'example': '--site_ids "[\"rimini-01\"]"',
    }
    TIME_RANGE = {
        'aliases': ['--time_range', '--time', '--datetime_range', '--datetime', '--t'],
        'help': "Time range as two ISO 8601 UTC0 strings (start, end).",
        'default': None,
        'example': '--time_range 2025-01-21T08:00:00 2025-01-22T23:00:00',
    }
    STRICT_TIME_RANGE = {
        'aliases': ['--strict_time_range', '--strict', '--str'],
        'help': "Enable strict time range to check data availability until requested end time.",
        'default': False,
        'example': '--strict_time_range',
    }
    OUT = {
        'aliases': ['--out', '--output', '--o'],
        'help': "Output file path for the retrieved data.",
        'default': None,
        'example': '--out /path/to/output.geojson',
    }
    OUT_FORMAT = {
        'aliases': ['--out_format', '--output_format', '--of'],
        'help': "Output format of the retrieved data.",
        'default': None,
        'example': '--out_format geojson',
    }
    BUCKET_DESTINATION = {
        'aliases': ['--bucket_destination', '--bucket', '--s3'],
        'help': "Destination bucket for the output data.",
        'default': None,
        'example': '--bucket_destination s3://my-bucket/path/to/prefix',
    }


def _parse_json_option(ctx, param, value):
    """
    _parse_json_option - parse a JSON string CLI option into a Python object.
    """
    import json
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        raise click.BadParameter(f'{param.name} must be a valid JSON string')


@click.command()

# -----------------------------------------------------------------------------
# Specific options of your CLI application
# -----------------------------------------------------------------------------
@click.option(
    *_ARG_NAMES.LAT_RANGE['aliases'],
    callback=lambda ctx, param, value: list(value) if value else None,
    type=float, nargs=2, default=_ARG_NAMES.LAT_RANGE['default'],
    help=_ARG_NAMES.LAT_RANGE['help'],
)
@click.option(
    *_ARG_NAMES.LONG_RANGE['aliases'],
    callback=lambda ctx, param, value: list(value) if value else None,
    type=float, nargs=2, default=_ARG_NAMES.LONG_RANGE['default'],
    help=_ARG_NAMES.LONG_RANGE['help'],
)
@click.option(
    *_ARG_NAMES.SITE_IDS['aliases'],
    callback=_parse_json_option,
    type=str, default=_ARG_NAMES.SITE_IDS['default'],
    help=_ARG_NAMES.SITE_IDS['help'],
)
@click.option(
    *_ARG_NAMES.TIME_RANGE['aliases'],
    callback=lambda ctx, param, value: list(value) if value else None,
    type=str, nargs=2, default=_ARG_NAMES.TIME_RANGE['default'],
    help=_ARG_NAMES.TIME_RANGE['help'],
)
@click.option(
    *_ARG_NAMES.STRICT_TIME_RANGE['aliases'],
    is_flag=True, default=_ARG_NAMES.STRICT_TIME_RANGE['default'],
    help=_ARG_NAMES.STRICT_TIME_RANGE['help'],
)
@click.option(
    *_ARG_NAMES.OUT['aliases'],
    type=str, default=_ARG_NAMES.OUT['default'],
    help=_ARG_NAMES.OUT['help'],
)
@click.option(
    *_ARG_NAMES.OUT_FORMAT['aliases'],
    type=click.Choice(['geojson', 'dataframe'], case_sensitive=False), default=_ARG_NAMES.OUT_FORMAT['default'],
    help=_ARG_NAMES.OUT_FORMAT['help'],
)
@click.option(
    *_ARG_NAMES.BUCKET_DESTINATION['aliases'],
    type=str, default=_ARG_NAMES.BUCKET_DESTINATION['default'],
    help=_ARG_NAMES.BUCKET_DESTINATION['help'],
)

# -----------------------------------------------------------------------------
# Common options to all Gecosistema CLI applications
# -----------------------------------------------------------------------------
@click.option(
    '--backend',
    type=click.STRING, required=False, default=None,
    help="The backend to use for sending back progress status updates to the backend server."
)
@click.option(
    '--jid',
    type=click.STRING, required=False, default=None,
    help="The job ID to use for sending back progress status updates to the backend server. If not provided, it will be generated automatically."
)
@click.option(
    '--version',
    is_flag=True, required=False, default=False,
    help="Show the version of the package."
)
@click.option(
    '--debug',
    is_flag=True, required=False, default=False,
    help="Debug mode."
)
@click.option(
    '--verbose',
    is_flag=True, required=False, default=False,
    help="Print some words more about what is doing."
)

def cli_run_xbeach_retriever(**kwargs):
    """
    main_click - main function for the CLI application
    """
    output = run_xbeach_retriever(**kwargs)

    Logger.debug(pprint.pformat(output))

    return output


def run_xbeach_retriever(
    # --- Specific options ---
    lat_range=None,
    long_range=None,
    site_ids=None,
    time_range=None,
    strict_time_range=False,
    out=None,
    out_format=None,
    bucket_destination=None,

    # --- Common options ---
    backend=None,
    jid=None,
    version=False,
    debug=False,
    verbose=False
):
    """
    main_python - main function
    """

    try:

        # DOC: -- Init logger + cli settings + handle version and debug -------
        t0, jid = prologo(backend, jid, version, verbose, debug)

        # DOC: -- Run the XBeach retriever process ----------------------------
        XBeachRetriever = _XBeachRetriever()
        results = XBeachRetriever.run(
            lat_range=lat_range,
            long_range=long_range,
            site_ids=site_ids,
            time_range=time_range,
            strict_time_range=strict_time_range,
            out=out,
            out_format=out_format,
            bucket_destination=bucket_destination,
        )

    except StatusException as err:
        results = {
            'status': err.status,
            'body': {
                'message': str(err),
                ** ({"traceback": traceback.format_exc()} if debug else dict())
            }
        }
    except Exception as e:
        results = {
            "status": StatusException.ERROR,
            "body": {
                "error": str(e),
                ** ({"traceback": traceback.format_exc()} if debug else dict())
            }
        }

    # DOC: -- Cleanup the temporary files if needed ---------------------------
    epilogo(t0, backend, jid)

    return results
