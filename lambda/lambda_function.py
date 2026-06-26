from process_xbeach_retriever import parse_event
from process_xbeach_retriever import run_xbeach_retriever as main_function


def lambda_handler(event, context):
    """
    lambda_handler - lambda function
    """
    kwargs = parse_event(event, main_function)

    res = main_function(**kwargs)

    return {
        "statusCode": 200,
        "body": {
            "result": res
        }
    }


if __name__ == "__main__":
    event = {
        "lat_range": [44, 44.5],
        "long_range": [12.2, 12.8],
        "time_range": ["2025-01-21T08:00:00", "2025-01-22T23:00:00"],
        "out_format": "geojson",
        "debug": "false"
    }

    kwargs = parse_event(event, main_function)
    res = main_function(**kwargs)
    print(res)
