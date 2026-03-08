from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from arbitrage.engine import find_opportunities
import datetime

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/arbitrage")
def get_arbitrage_data():
    """Fetch arbitrage data from Polymarket and Kalshi."""
    # Fetch data
    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    response = {
        "timestamp": datetime.datetime.now().isoformat(),
        "polymarket": poly_data,
        "kalshi": kalshi_data,
        "checks": [],
        "opportunities": [],
        "errors": []
    }

    if poly_err:
        response["errors"].append(poly_err)
    if kalshi_err:
        response["errors"].append(kalshi_err)

    if not poly_data or not kalshi_data:
        return response

    # Find opportunities using arbitrage engine
    opportunities, checks = find_opportunities(poly_data, kalshi_data)

    response["opportunities"] = opportunities
    response["checks"] = checks

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
