from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('submit-order/', views.submit_order, name='submit_order'),
    path('cancel-order/<int:order_id>/', views.cancel_order_view, name='cancel_order'),
]