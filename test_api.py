import base64
import time
import requests
import json

# Your actual API URL
API_URL = "https://7a8zj1nbya.execute-api.ap-south-1.amazonaws.com/prod"

# 1. Read and encode a test image
image_path = "image.png" 
with open(image_path, "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

print("1. Submitting image to API...")
resp = requests.post(f"{API_URL}/audit", json={
    "image_b64": image_b64,
    "lang": "en"
})
audit_id = resp.json()["audit_id"]
print(f"   Received audit_id: {audit_id}")

# 2. Poll the status endpoint
print("\n2. Polling for results (Bedrock takes ~10 seconds)...")
while True:
    status_resp = requests.get(f"{API_URL}/status/{audit_id}")
    data = status_resp.json()
    
    if data["status"] == "complete":
        print("\n✅ AUDIT COMPLETE!")
        print(json.dumps(data, indent=2))
        break
    elif data["status"] == "failed":
        print("\n❌ AUDIT FAILED!")
        print(json.dumps(data, indent=2))
        break
        
    print("   Still processing...")
    time.sleep(2)
