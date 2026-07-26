from waitress import serve

from app import app


if __name__ == "__main__":
    print(
        "Starting RateMyDoctor at http://127.0.0.1:5001",
        flush=True
    )

    serve(
        app,
        host="127.0.0.1",
        port=5001,
        threads=8
    )