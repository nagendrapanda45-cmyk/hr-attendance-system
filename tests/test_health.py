from django.test import Client

def test_health_check():
    client = Client()
    response = client.get('/api/v1/health/')
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "django"}

def test_ready_check():
    client = Client()
    response = client.get('/api/v1/ready/')
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}