# process-xbeach-retriever

PyGeoAPI process to retrieve **XBeach** runup model output for a given time range and location bounds.

## Overview

This package retrieves XBeach binary `rugau` `.dat` files from the ARPAE FTPS server, parses them into per-site runup time series, and returns them as a GeoJSON feature collection. It can run in two modes:

- **local**: the retriever logic runs in-process (default, backward compatible)
- **lambda**: the PyGeoAPI processor invokes an AWS Lambda function that performs the retrieval

The result feature collection can optionally be uploaded to an S3 bucket.

## Installation

```bash
pip install .
```

To include the PyGeoAPI processor:

```bash
pip install ".[pygeoapi]"
```

## Usage

### CLI

```bash
xbeach-retriever \
  --lat_range 44 44.5 \
  --long_range 12.2 12.8 \
  --time_range 2025-01-21T08:00:00 2025-01-22T23:00:00 \
  --out_format geojson
```

### Python

```python
from process_xbeach_retriever import run_xbeach_retriever

result = run_xbeach_retriever(
    lat_range=[44, 44.5],
    long_range=[12.2, 12.8],
    time_range=["2025-01-21T08:00:00", "2025-01-22T23:00:00"],
    out_format="geojson",
)
```

## Configuration

Copy `.env.example` to `.env` and set the values:

| Variable | Description |
| --- | --- |
| `XBEACH_PROCESSOR_MODE` | `local` or `lambda` |
| `XBEACH_RETRIEVER_LAMBDA_FUNCTION_NAME` | Lambda function name (required when mode is `lambda`) |
| `FTPS_ARPAE_HOST` | ARPAE FTPS server host |
| `FTPS_ARPAE_USERNAME` | ARPAE FTPS username |
| `FTPS_ARPAE_PASSWORD` | ARPAE FTPS password |
| `AWS_REGION` | AWS region (default `us-east-1`) |
| `INT_API_TOKEN` | Token required by the PyGeoAPI process |

## Parameters

| Parameter | Description |
| --- | --- |
| `lat_range` | Latitude range `[lat_min, lat_max]` in EPSG:4326 |
| `long_range` | Longitude range `[long_min, long_max]` in EPSG:4326 |
| `site_ids` | List of site IDs (subset of `rimini-01`, `riccione-01`, `riccione-02`) |
| `time_range` | Time range `[time_start, time_end]` in ISO-8601 (UTC) |
| `strict_time_range` | Check data availability until requested end time |
| `out` | Output file path |
| `out_format` | Output format: `geojson` or `dataframe` |
| `bucket_destination` | Optional S3 destination for the output |

## Deployment

A GitHub Actions workflow (`.github/workflows/docker-build.yml`) builds the Docker image and pushes it to the AWS ECR registry, then creates or updates the `xbeach-retriever` Lambda function.

## License

MIT
