import requests
def get_data(*a,**k):
    r = requests.get(*a,**k); r.raise_for_status(); return r.json()
