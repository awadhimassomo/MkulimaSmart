"""
Modular prediction system for Mkulima Smart
Handles multiple prediction types including:
- Rainfall prediction
- Crop yield prediction
- Pest/disease risk prediction
- Irrigation recommendations
- Sowing calendar recommendations
"""

import pandas as pd
import numpy as np
import logging
from prophet import Prophet
from django.utils import timezone
from datetime import datetime, timedelta

# Import models from both apps
from website.models import Farm, WeatherData, RainForecast
from predictions.models import CropData, SoilData, PredictionResult

logger = logging.getLogger(__name__)

class BasePredictionModel:
    """Base class for all prediction models"""
    
    def __init__(self):
        self.model_name = "base"
        self.description = "Base prediction model"
    
    def get_training_data(self, **kwargs):
        """Get training data for the model - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement this method")
    
    def train(self, **kwargs):
        """Train the model - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement this method")
    
    def predict(self, **kwargs):
        """Make predictions - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement this method")
    
    def save_prediction(self, farm, prediction_type, prediction_data):
        """Save prediction results to database"""
        PredictionResult.objects.update_or_create(
            farm=farm,
            type=prediction_type,
            defaults={'prediction_data': prediction_data}
        )
        logger.info(f"Saved {prediction_type} prediction for farm {farm.id}")


class RainfallPredictionModel(BasePredictionModel):
    """Rainfall prediction model using Prophet"""
    
    def __init__(self):
        super().__init__()
        self.model_name = "rainfall"
        self.description = "Rainfall prediction using Prophet"
        
    def get_training_data(self, farm, min_samples=10):
        """Get historical rainfall data for the farm"""
        weather_data = WeatherData.objects.filter(farm=farm).order_by('date')
        
        if len(weather_data) < min_samples:
            logger.warning(f"Not enough historical data for farm {farm.id} to make reliable predictions")
            return None
            
        # Convert to DataFrame for Prophet
        df = pd.DataFrame(list(weather_data.values('date', 'rainfall_mm')))
        df.columns = ['ds', 'y']  # Prophet expects these column names
        
        # Handle zeros and missing values
        df['y'] = df['y'].replace(0, 0.01)  # Replace zeros with small value
        df['y'] = df['y'].fillna(0.01)  # Fill missing values
        
        return df
    
    def train(self, training_data, seasonality_mode='multiplicative'):
        """Train Prophet model on historical weather data"""
        if training_data is None or len(training_data) < 10:
            return None
            
        try:
            # Initialize and train Prophet model
            model = Prophet(
                daily_seasonality=True,
                yearly_seasonality=True,
                seasonality_mode=seasonality_mode
            )
            model.fit(training_data)
            return model
        except Exception as e:
            logger.error(f"Error training rainfall model: {str(e)}")
            return None
    
    def predict(self, farm, days_to_predict=14):
        """Train model and make rainfall predictions"""
        training_data = self.get_training_data(farm)
        if training_data is None:
            return False
            
        model = self.train(training_data)
        if model is None:
            return False
            
        try:
            # Make future predictions
            future = model.make_future_dataframe(periods=days_to_predict)
            forecast = model.predict(future)
            
            # Save predictions to database
            for _, row in forecast.tail(days_to_predict).iterrows():
                date = row['ds'].to_pydatetime().date()
                rain_mm = max(0, row['yhat'])  # Ensure non-negative rainfall
                confidence = min(1.0, max(0.1, 1.0 - (row['yhat_upper'] - row['yhat_lower']) / max(1.0, row['yhat'])))
                
                # Update or create forecast in RainForecast model
                RainForecast.objects.update_or_create(
                    farm=farm,
                    forecast_date=date,
                    defaults={
                        'predicted_rain_mm': rain_mm,
                        'confidence': confidence
                    }
                )
            
            # Also save as a generic prediction result
            prediction_data = {
                'forecast_dates': [row['ds'].strftime('%Y-%m-%d') for _, row in forecast.tail(days_to_predict).iterrows()],
                'predicted_rain_mm': [max(0, row['yhat']) for _, row in forecast.tail(days_to_predict).iterrows()],
                'lower_bounds': [max(0, row['yhat_lower']) for _, row in forecast.tail(days_to_predict).iterrows()],
                'upper_bounds': [max(0, row['yhat_upper']) for _, row in forecast.tail(days_to_predict).iterrows()],
                'updated_at': timezone.now().isoformat()
            }
            
            self.save_prediction(farm, 'rainfall', prediction_data)
            logger.info(f"Successfully updated rainfall forecast for farm {farm.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error making rainfall prediction for farm {farm.id}: {str(e)}")
            return False


class YieldPredictionModel(BasePredictionModel):
    """Crop yield prediction model"""
    
    def __init__(self):
        super().__init__()
        self.model_name = "yield"
        self.description = "Crop yield prediction"
    
    def get_training_data(self, crop_data):
        """Gather data needed for yield prediction"""
        farm = crop_data.farm
        
        # Get weather data for this farm
        weather_data = WeatherData.objects.filter(
            farm=farm,
            date__gte=crop_data.planting_date
        ).order_by('date')
        
        # Get soil data if available
        try:
            soil_data = SoilData.objects.filter(
                lat__range=(farm.latitude-0.01, farm.latitude+0.01),
                lon__range=(farm.longitude-0.01, farm.longitude+0.01)
            ).latest('date')
        except SoilData.DoesNotExist:
            soil_data = None
        
        # Basic features for yield prediction
        features = {
            'crop_type': crop_data.crop_type,
            'variety': crop_data.variety,
            'planting_date': crop_data.planting_date,
            'field_size_acres': crop_data.field_size_acres,
            'days_since_planting': (timezone.now().date() - crop_data.planting_date).days,
            'total_rainfall_mm': sum(w.rainfall_mm for w in weather_data),
            'avg_temperature': np.mean([w.temperature for w in weather_data]) if weather_data else None,
            'soil_ph': soil_data.ph if soil_data else None,
            'soil_moisture': soil_data.moisture if soil_data else None,
        }
        
        return features
    
    def train(self, **kwargs):
        """
        For now, use rule-based model instead of ML training
        Could be expanded to XGBoost or other ML model in the future
        """
        return self  # No training needed for rule-based model
    
    def predict(self, crop_data):
        """Make yield prediction based on crop, weather, and soil data"""
        farm = crop_data.farm
        features = self.get_training_data(crop_data)
        
        # Simple rule-based yield estimate (can be replaced with ML model)
        base_yield = {
            'maize': 2.5,  # 2.5 tons/acre for maize
            'rice': 3.0,
            'beans': 1.2,
            'cassava': 10.0,
            'potato': 8.0,
            'tomato': 12.0
        }.get(crop_data.crop_type.lower(), 2.0)  # Default yield if crop not in list
        
        # Adjust based on rainfall (optimal range depends on crop)
        optimal_rainfall = {
            'maize': 600,
            'rice': 1000,
            'beans': 400,
            'cassava': 500,
            'potato': 700,
            'tomato': 600
        }.get(crop_data.crop_type.lower(), 500)
        
        total_rain = features['total_rainfall_mm'] or 0
        rain_factor = min(1.2, max(0.5, 1.0 - abs(total_rain - optimal_rainfall) / optimal_rainfall))
        
        # Adjust based on soil quality if available
        soil_factor = 1.0
        if features['soil_ph'] is not None:
            # Most crops prefer pH 5.5-7.0
            optimal_ph = 6.5
            soil_factor *= min(1.1, max(0.7, 1.0 - 0.2 * abs(features['soil_ph'] - optimal_ph)))
        
        # Calculate estimated yield
        estimated_yield = base_yield * rain_factor * soil_factor
        
        # Calculate confidence based on data availability
        confidence_factors = []
        if features['total_rainfall_mm'] is not None:
            confidence_factors.append(0.8)
        if features['avg_temperature'] is not None:
            confidence_factors.append(0.7)
        if features['soil_ph'] is not None:
            confidence_factors.append(0.6)
        
        confidence = min(0.95, sum(confidence_factors) / max(1, len(confidence_factors)))
        
        # Create prediction result
        prediction_data = {
            'crop_type': crop_data.crop_type,
            'planting_date': crop_data.planting_date.isoformat(),
            'estimated_yield_tons_per_acre': round(estimated_yield, 2),
            'total_estimated_yield': round(estimated_yield * features['field_size_acres'], 2),
            'confidence': round(confidence, 2),
            'factors': {
                'rainfall_adequacy': round(rain_factor, 2),
                'soil_quality': round(soil_factor, 2)
            },
            'updated_at': timezone.now().isoformat()
        }
        
        self.save_prediction(farm, 'yield', prediction_data)
        logger.info(f"Successfully created yield prediction for crop {crop_data.id}")
        return True


class PestDiseasePredictionModel(BasePredictionModel):
    """Pest and disease risk prediction model"""
    
    def __init__(self):
        super().__init__()
        self.model_name = "pest_disease"
        self.description = "Pest and disease risk prediction"
    
    def get_training_data(self, farm, days_lookback=14):
        """Get recent weather data for pest/disease risk assessment"""
        start_date = timezone.now().date() - timedelta(days=days_lookback)
        
        # Get recent weather data
        weather_data = WeatherData.objects.filter(
            farm=farm,
            date__gte=start_date
        ).order_by('date')
        
        if len(weather_data) < 7:  # Need at least a week of data
            logger.warning(f"Not enough recent weather data for farm {farm.id}")
            return None
            
        # Extract relevant features
        features = {
            'avg_humidity': np.mean([w.humidity for w in weather_data]),
            'max_humidity': max([w.humidity for w in weather_data]),
            'avg_temperature': np.mean([w.temperature for w in weather_data]),
            'total_rainfall': sum([w.rainfall_mm for w in weather_data]),
            'consecutive_wet_days': self._calculate_wet_streak(weather_data)
        }
        
        return features
    
    def _calculate_wet_streak(self, weather_data):
        """Calculate the longest streak of consecutive wet days"""
        wet_threshold = 2.0  # mm of rain to consider a day "wet"
        
        current_streak = 0
        max_streak = 0
        
        for w in weather_data:
            if w.rainfall_mm >= wet_threshold:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
                
        return max_streak
    
    def train(self, **kwargs):
        """Rule-based model, no training required"""
        return self
        
    def predict(self, farm, crop_type):
        """Predict pest and disease risk based on recent weather conditions"""
        features = self.get_training_data(farm)
        if features is None:
            return False
        
        # Disease risk factors (these would ideally be crop-specific)
        # High humidity and moderate temperatures favor fungal diseases
        # Long periods of leaf wetness (rain/humidity) increase risk
        disease_risk = 0.0
        
        if features['avg_humidity'] > 70:
            disease_risk += 0.3
            
        if features['max_humidity'] > 85:
            disease_risk += 0.2
            
        if 18 <= features['avg_temperature'] <= 28:  # Optimal for many fungal diseases
            disease_risk += 0.3
            
        disease_risk += min(0.3, features['consecutive_wet_days'] * 0.05)
        disease_risk = min(1.0, disease_risk)
        
        # Pest risk factors
        # Different for different crops and regions
        pest_risk = 0.0
        
        if features['avg_temperature'] > 25:
            pest_risk += 0.3  # Warmer temps speed insect development
            
        if features['total_rainfall'] < 10:
            pest_risk += 0.2  # Dry conditions favor some pests
            
        pest_risk = min(1.0, pest_risk)
        
        # Combined risk and specific concerns
        concerns = []
        recommendations = []
        
        # Example logic for specific pest/disease warnings
        if disease_risk > 0.6 and crop_type.lower() == 'tomato':
            concerns.append({
                'type': 'disease',
                'name': 'Late Blight',
                'risk_level': 'high',
                'description': 'Fungal disease common in wet conditions'
            })
            recommendations.append('Consider preventative fungicide application')
            
        if pest_risk > 0.5 and crop_type.lower() == 'maize':
            concerns.append({
                'type': 'pest',
                'name': 'Fall Armyworm',
                'risk_level': 'medium',
                'description': 'Common during warm, dry periods'
            })
            recommendations.append('Scout fields for eggs and larvae')
        
        # Create prediction result
        prediction_data = {
            'overall_disease_risk': round(disease_risk, 2),
            'overall_pest_risk': round(pest_risk, 2),
            'concerns': concerns,
            'recommendations': recommendations,
            'weather_factors': {
                'avg_humidity': round(features['avg_humidity'], 1),
                'total_rainfall': round(features['total_rainfall'], 1),
                'consecutive_wet_days': features['consecutive_wet_days']
            },
            'updated_at': timezone.now().isoformat()
        }
        
        self.save_prediction(farm, 'pest_disease', prediction_data)
        logger.info(f"Successfully created pest/disease risk assessment for farm {farm.id}")
        return True


class PredictionManager:
    """Central manager for all prediction models"""
    
    def __init__(self):
        self.rainfall_model = RainfallPredictionModel()
        self.yield_model = YieldPredictionModel()
        self.pest_disease_model = PestDiseasePredictionModel()
    
    def forecast_rainfall(self, farm_id, days=14):
        """Make rainfall forecast for a specific farm"""
        try:
            farm = Farm.objects.get(pk=farm_id)
            return self.rainfall_model.predict(farm, days_to_predict=days)
        except Farm.DoesNotExist:
            logger.error(f"Farm with ID {farm_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error forecasting rainfall: {str(e)}")
            return False
    
    def predict_yield(self, crop_id):
        """Predict yield for a specific crop"""
        try:
            crop = CropData.objects.get(pk=crop_id)
            return self.yield_model.predict(crop)
        except CropData.DoesNotExist:
            logger.error(f"Crop data with ID {crop_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error predicting yield: {str(e)}")
            return False
    
    def assess_pest_disease_risk(self, farm_id, crop_type):
        """Assess pest and disease risk for a farm and crop type"""
        try:
            farm = Farm.objects.get(pk=farm_id)
            return self.pest_disease_model.predict(farm, crop_type)
        except Farm.DoesNotExist:
            logger.error(f"Farm with ID {farm_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error assessing pest/disease risk: {str(e)}")
            return False
    
    def update_all_forecasts(self):
        """Update forecasts for all farms"""
        farms = Farm.objects.all()
        success_count = 0
        
        for farm in farms:
            logger.info(f"Updating rainfall forecast for farm {farm.id}: {farm.name}")
            
            # Update rainfall forecast
            if self.rainfall_model.predict(farm):
                success_count += 1
                
            # Update pest/disease risk if primary crop is known
            if farm.primary_crop:
                self.pest_disease_model.predict(farm, farm.primary_crop)
            
            # Update yield predictions for all crops on this farm
            for crop in CropData.objects.filter(farm=farm):
                self.yield_model.predict(crop)
                
        logger.info(f"Updated forecasts for {success_count} out of {len(farms)} farms")
        return success_count
