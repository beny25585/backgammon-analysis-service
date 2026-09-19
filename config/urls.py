"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from analysis.api.views import health, receive_match
from analysis.api.results import match_results

urlpatterns = [
    path("api/v1/internal/results/", match_results, name="analysis-results"),
    path("api/v1/internal/results/<uuid:analysis_id>/", match_results, name="analysis-result"),
    path('admin/', admin.site.urls),
    # Analysis API
    path("api/v1/health/", health, name="health"),

    # Internal Game -> Analysis API
    path(
        "api/v1/internal/matches/",
        receive_match,
        name="receive-match",
    ),
]
