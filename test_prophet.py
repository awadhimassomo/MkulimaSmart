from prophet import Prophet
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Sample weather-like dataset (you'll later replace with real rainfall data)
df = pd.DataFrame({
    'ds': pd.date_range(start='2025-01-01', periods=30, freq='D'),
    'y': [2.1, 2.4, 2.6, 2.9, 3.1, 3.2, 3.5, 3.6, 3.2, 3.0, 
          2.8, 2.7, 2.5, 2.3, 2.0, 2.2, 2.6, 2.9, 3.0, 3.4, 
          3.7, 3.8, 4.0, 3.9, 3.6, 3.3, 3.1, 2.8, 2.5, 2.2]
})

# Initialize the model with parameters similar to our weather_utils.py
model = Prophet(
    daily_seasonality=True,
    yearly_seasonality=True,
    seasonality_mode='multiplicative'  # Good for rainfall data
)

print("Fitting Prophet model...")
model.fit(df)
print("Model fitted successfully!")

# Forecast the next 14 days (same as in our production code)
days_to_predict = 14
future = model.make_future_dataframe(periods=days_to_predict)
forecast = model.predict(future)

# Print forecasted values for the future dates
print("\nFORECASTED RAINFALL (next 14 days):")
print(forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days_to_predict))

# Optional: Create and save plots
try:
    print("\nGenerating forecast plots...")
    fig1 = model.plot(forecast)
    plt.title('Rainfall Prediction')
    plt.ylabel('Rainfall (mm)')
    plt.savefig('rainfall_forecast.png')
    print("Saved forecast plot as 'rainfall_forecast.png'")
    
    fig2 = model.plot_components(forecast)
    plt.savefig('rainfall_components.png')
    print("Saved components plot as 'rainfall_components.png'")
except Exception as e:
    print(f"Could not generate plots: {e}")

print("\nProphet test completed successfully!")
print("The model is ready to be used for real rainfall predictions.")
