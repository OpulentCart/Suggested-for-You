import psycopg2
import os
from pinecone import Pinecone
from django.conf import settings
from rest_framework.response import Response
from rest_framework.decorators import api_view
from dotenv import load_dotenv

load_dotenv()

# Initialize Pinecone
api_key = os.getenv("PINECONE_API_KEY")
pc = Pinecone(api_key=api_key)
index_name = "related-products"
index = pc.Index(index_name)

def get_db_connection():
    """Establish a connection to PostgreSQL."""
    return psycopg2.connect(
        dbname=settings.DATABASES['default']['NAME'],
        user=settings.DATABASES['default']['USER'],
        password=settings.DATABASES['default']['PASSWORD'],
        host=settings.DATABASES['default']['HOST'],
        port=settings.DATABASES['default']['PORT'],
    )

def get_recent_interactions(user_id, limit=10):
    """Fetch recent product interactions of a user from PostgreSQL."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
        SELECT product_id FROM user_interactions
        WHERE user_id = %s
        ORDER BY timestamp DESC
        LIMIT %s;
        """
        cursor.execute(query, (user_id, limit))
        products = [row[0] for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print("PostgreSQL Error:", err)
        products = []
    finally:
        cursor.close()
        conn.close()
    return list(set(products))

def get_product_details(product_ids):
    """Fetch product details from PostgreSQL for given product IDs."""
    if not product_ids:
        return []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
        SELECT product_id, name, brand, price, main_image 
        FROM product 
        WHERE product_id IN %s;
        """
        cursor.execute(query, (tuple(product_ids),))
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "brand": row[2],
                "price": float(row[3]),  # Convert Decimal to float
                "main_image": row[4]
            }
            for row in rows
        ]
    except psycopg2.Error as err:
        print("PostgreSQL Error fetching product details:", err)
        return []
    finally:
        cursor.close()
        conn.close()

def get_similar_products(product_id, top_k=10):
    """Fetch similar products from Pinecone with similarity scores."""
    try:
        query_result = index.query(id=str(product_id), top_k=top_k, include_metadata=True)
        similar_products = [
            {"id": match['id'], "score": match['score']}
            for match in query_result.get('matches', [])
        ]
    except Exception as e:
        print(f"Error querying Pinecone for product {product_id}: {e}")
        similar_products = []
    return similar_products

@api_view(['GET'])
def generate_recommendations(request, user_id):
    """API to generate recommendations for a given user."""
    # Get recent interactions
    recent_products = get_recent_interactions(user_id)
    recommendations = {}

    # Fetch similar products with scores from Pinecone
    for product_id in recent_products:
        similar_products = get_similar_products(product_id)
        for product in similar_products:
            pid = product['id']
            if pid not in recommendations:
                recommendations[pid] = product['score']
            else:
                # Use the highest score if a product appears multiple times
                recommendations[pid] = max(recommendations[pid], product['score'])

    # Get product details from PostgreSQL
    product_ids = list(recommendations.keys())
    product_details = get_product_details(product_ids)

    # Combine details with scores
    recommended_products = [
        {
            "id": product["id"],
            "name": product["name"],
            "brand": product["brand"],
            "price": product["price"],
            "main_image": product["main_image"],
            "hybrid_score": float(recommendations.get(str(product["id"]), 0))  # Convert to float
        }
        for product in product_details
    ]

    # Sort by hybrid_score and limit to top 5 (or adjust as needed)
    recommended_products = sorted(recommended_products, key=lambda x: x["hybrid_score"], reverse=True)[:10]

    return Response({
        "user_id": user_id,
        "recommended_products": recommended_products
    })