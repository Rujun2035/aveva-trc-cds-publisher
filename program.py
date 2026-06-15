#!/usr/bin/env python3
"""
AVEVA .TRC to Connect Data Services Publisher
=============================================
This application reads AVEVA Process Simulation .trc trace files,
parses the post-solution analysis data (mass/energy conservation
relationships), and publishes the results to AVEVA Connect Data Services
via the Open Message Format (OMF) protocol.

Usage:
    python program.py --file data/your_file.trc
    python program.py --file data/your_file.trc --dry-run

Requirements:
    pip install -r requirements.txt

Configuration:
    Edit appsettings.json with your CDS credentials.
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone

from trc_parser import TRCParser
from omf_publisher import OMFPublisher
from models import (
    ActiveConstraintType,
    SensitivityType,
    ObjectiveSensitivityType,
    ConstraintSensitivityType,
    TopContributorType
)


def load_config(config_path="appsettings.json"):
    """Load configuration from appsettings.json"""
    if not os.path.exists(config_path):
        print(f"ERROR: Configuration file '{config_path}' not found!")
        print("Please rename 'appsettings.placeholder.json' to 'appsettings.json'")
        print("and fill in your AVEVA Connect credentials.")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    required = ["Resource", "NamespaceId", "Tenant", "ClientId", "ClientSecret"]
    missing = [field for field in required if not config.get(field) or "PLACEHOLDER" in str(config.get(field, ""))]
    
    if missing:
        print(f"ERROR: Missing or placeholder values in config: {missing}")
        print("Please update appsettings.json with your actual credentials.")
        sys.exit(1)
    
    return config


def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        description="AVEVA .TRC to Connect Data Services Publisher"
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to the .trc file to parse and publish"
    )
    parser.add_argument(
        "--config", "-c",
        default="appsettings.json",
        help="Path to configuration file (default: appsettings.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the file but don't publish to CDS (for testing)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: File '{args.file}' not found!")
        sys.exit(1)

    print("="*60)
    print("  AVEVA .TRC to Connect Data Services Publisher")
    print("="*60)
    print()

    # Step 1: Parse the .trc file
    print("[Step 1/4] Parsing .trc file...")
    trc_parser = TRCParser()
    parsed_data = trc_parser.parse_file(args.file)
    
    print(f"  Found {len(parsed_data['active_constraints'])} active constraint pairings")
    print(f"  Found {len(parsed_data['solution_sensitivities'])} solution sensitivities")
    print(f"  Found {len(parsed_data['objective_sensitivities'])} objective function sensitivities")
    print(f"  Found {len(parsed_data['constraint_sensitivities'])} constraint sensitivities")
    print(f"  Found {len(parsed_data['top_contributors'])} top contributors")
    print()

    if args.dry_run:
        print("[DRY RUN] Skipping publication to CDS.")
        print("\nParsed data preview:")
        print(json.dumps(parsed_data, indent=2, default=str))
        return

    # Step 2: Load configuration
    print("[Step 2/4] Loading configuration...")
    config = load_config(args.config)
    print(f"  Endpoint: {config['Resource']}")
    print(f"  Namespace: {config['NamespaceId']}")
    print()

    # Step 3: Connect to CDS and authenticate
    print("[Step 3/4] Connecting to AVEVA Connect Data Services...")
    publisher = OMFPublisher(config)
    publisher.authenticate()
    print("  Authentication successful")
    print()

    # Step 4: Publish data
    print("[Step 4/4] Publishing data to CDS...")
    
    print("  Sending OMF Type definitions...")
    publisher.send_types()
    print("    Types created")
    
    print("  Sending OMF Container definitions...")
    publisher.send_containers(parsed_data)
    print("    Containers created")
    
    print("  Sending data values...")
    publisher.send_data(parsed_data)
    print("    Data published successfully")
    
    print()
    print("="*60)
    print("  SUCCESS! All data published to Connect Data Services.")
    print("="*60)
    print()
    print("You can now view your data in AVEVA Connect:")
    print(f"  {config['Resource']}/namespaces/{config['NamespaceId']}/streams")
    print()


if __name__ == "__main__":
    main()
