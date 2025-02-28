from django.urls import path
from .views import generate_recommendations

urlpatterns = [
    path('recommendations/<int:user_id>/', generate_recommendations, name='generate_recommendations'),
]
