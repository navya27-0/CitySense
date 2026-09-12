"""Database Initialization Script for BusSense-AI.

Idempotently creates the PostgreSQL database, enables the PostGIS spatial extension,
generates all tables with GiST spatial indexes, and optionally inserts initial seed data.

Usage:
    python scripts/init_db.py [--seed]
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text
from backend.config import settings
from backend.database import engine, Base, init_db, check_db_connection
import backend.models as models
from backend.models.spatial_utils import point_from_lat_lon


def ensure_database_exists():
    """Connects to default 'postgres' database to ensure the target database exists."""
    print(f"[*] Checking if database '{settings.DB_NAME}' exists on {settings.DB_HOST}:{settings.DB_PORT}...")
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (settings.DB_NAME,))
        exists = cursor.fetchone()

        if not exists:
            print(f"[+] Database '{settings.DB_NAME}' does not exist. Creating...")
            cursor.execute(f'CREATE DATABASE "{settings.DB_NAME}";')
            print(f"[OK] Database '{settings.DB_NAME}' created successfully.")
        else:
            print(f"[OK] Database '{settings.DB_NAME}' already exists.")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[!] Warning during database existence check: {e}")
        print("    Proceeding directly to table creation on target database URL.")


def seed_initial_data():
    """Inserts mock routes and buses for demo and testing purposes."""
    print("[*] Seeding initial route and fleet fixtures...")
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        # 1. Create sample Hyderabad transit routes
        routes_data = [
            {"route_id": "216", "route_name": "Mehdipatnam to Hitec City", "start_location": "Mehdipatnam Terminal", "destination": "Cyber Towers / Hitec City"},
            {"route_id": "10", "route_name": "Secunderabad to Charminar", "start_location": "Secunderabad Station", "destination": "Charminar Bus Station"},
            {"route_id": "49", "route_name": "Dilsukhnagar to Jubilee Hills", "start_location": "Dilsukhnagar Terminal", "destination": "Jubilee Hills Checkpost"},
        ]

        for r_data in routes_data:
            existing = db.query(models.Route).filter_by(route_id=r_data["route_id"]).first()
            if not existing:
                db.add(models.Route(**r_data))

        db.commit()

        # 2. Create sample Hyderabad buses
        buses_data = [
            {"bus_id": "BUS_101", "route_id": "216", "latitude": 17.3916, "longitude": 78.4350, "speed": 34.5, "heading": 115.0, "status": "active"},
            {"bus_id": "BUS_102", "route_id": "10", "latitude": 17.4340, "longitude": 78.5015, "speed": 26.0, "heading": 185.0, "status": "active"},
            {"bus_id": "BUS_103", "route_id": "49", "latitude": 17.3688, "longitude": 78.5247, "speed": 0.0, "heading": 0.0, "status": "idle"},
        ]

        for b_data in buses_data:
            existing = db.query(models.Bus).filter_by(bus_id=b_data["bus_id"]).first()
            if not existing:
                db.add(models.Bus(**b_data))
            else:
                existing.route_id = b_data["route_id"]
                existing.set_coordinates(b_data["latitude"], b_data["longitude"])
                existing.speed = b_data["speed"]
                existing.heading = b_data["heading"]
                existing.status = b_data["status"]

        db.commit()
        print("[OK] Seed data inserted successfully.")
    except Exception as e:
        db.rollback()
        print(f"[!] Error seeding initial data: {e}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL + PostGIS database for BusSense-AI")
    parser.add_argument("--seed", action="store_true", help="Insert initial demo routes and buses")
    args = parser.parse_args()

    print("==========================================================")
    print(" BusSense-AI Database Initialization (PostgreSQL + PostGIS)")
    print("==========================================================")
    
    # 1. Ensure DB exists
    ensure_database_exists()

    # 2. Enable PostGIS & Create Tables
    print(f"[*] Initializing PostGIS extension and database tables on '{settings.DB_NAME}'...")
    try:
        init_db()
        print("[OK] PostGIS extension verified and tables created successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to initialize tables: {e}")
        sys.exit(1)

    # 3. Verify Connection & PostGIS Status
    status = check_db_connection()
    if status["connected"]:
        print(f"[OK] Database connection verified on {status['host']}:{status['port']}/{status['database_name']}.")
        if status["postgis_installed"]:
            print(f"[OK] PostGIS Extension Active: {status['postgis_version']}")
        else:
            print("[!] PostGIS extension check returned false.")
    else:
        print(f"[ERROR] Database connection check failed: {status['error']}")
        sys.exit(1)

    # 4. Optional Seed Data
    if args.seed:
        seed_initial_data()

    print("\n[OK] Database initialization complete!")


if __name__ == "__main__":
    main()
