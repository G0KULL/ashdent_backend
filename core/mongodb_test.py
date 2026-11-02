import sys
import os

# Add the current directory to path so we can import 'core'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.mongodb import patients_collection
    
    print("--- MongoDB Connection Test ---")
    
    # Try to insert a dummy record
    test_data = {"test": "connection_success", "message": "MongoDB is working with Django!"}
    result = patients_collection.insert_one(test_data)
    print(f"✅ Success: Inserted document with ID: {result.inserted_id}")
    
    # Try to find it back
    found = patients_collection.find_one({"_id": result.inserted_id})
    print(f"✅ Success: Retrieved document: {found['message']}")
    
    # Clean up
    patients_collection.delete_one({"_id": result.inserted_id})
    print("✅ Success: Cleanup complete.")
    print("-------------------------------")
    print("Your MongoDB connection is READY to use.")

except Exception as e:
    print(f"❌ Error: Could not connect to MongoDB.")
    print(f"Details: {e}")
    print("\nMake sure MongoDB is running on your machine (localhost:27017).")
