from pymongo import MongoClient

# Initialize the MongoDB Client
# You can change the URI if you move to MongoDB Atlas later
client = MongoClient("mongodb://localhost:27017/")

# Access the Dental Clinic Database
db = client['dental_clinic_db']

# Define some common collections for easy access
patients_collection = db['patients']
medical_records_collection = db['medical_records']
inventory_collection = db['inventory']

def get_db():
    """Utility function to get the database instance"""
    return db
