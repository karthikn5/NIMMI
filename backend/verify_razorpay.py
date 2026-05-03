import os
import razorpay
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

print("--- Razorpay Credential Verifier ---")
print(f"Key ID: {RAZORPAY_KEY_ID}")
print(f"Key Secret: {'*' * len(RAZORPAY_KEY_SECRET) if RAZORPAY_KEY_SECRET else 'MISSING'}")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    print("\n[ERROR] Missing credentials in .env file.")
    exit(1)

try:
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    
    # Try to create a small test order
    print("\nAttempting to create a test order (INR 1)...")
    order = client.order.create({
        "amount": 100, # 100 paise = INR 1
        "currency": "INR",
        "receipt": "test_verification",
        "notes": {"info": "Verifying credentials"}
    })
    
    if "id" in order:
        print(f"\n[SUCCESS] Credentials are valid! Order ID: {order['id']}")
        print("You can now safely use these keys in Railway.")
    else:
        print("\n[FAILED] Unexpected response from Razorpay.")
        print(order)

except Exception as e:
    import traceback
    print(f"\n[ERROR] Authentication failed: {str(e)}")
    # traceback.print_exc()
    print("\nPlease check:")
    print("1. Are you using the correct Secret key?")
    print("2. Is your account active (Live or Test mode)?")
    print("3. Are you using a Test Key in Live mode or vice-versa?")
