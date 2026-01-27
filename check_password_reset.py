#!/usr/bin/env python3
"""
Quick verification script for the password reset feature.
Run this before deployment to ensure everything is configured correctly.
"""

import os
import sys
from dotenv import load_dotenv

def check_configuration():
    """Check if all required configuration is in place."""
    load_dotenv()
    
    print("\n" + "="*60)
    print("🔍 PASSWORD RESET FEATURE - CONFIGURATION CHECK")
    print("="*60 + "\n")
    
    checks = {
        "Brevo API Key": os.getenv("BREVO_API_KEY"),
        "Brevo Sender Email": os.getenv("BREVO_SENDER_EMAIL"),
        "Database URL": os.getenv("DATABASE_URL"),
    }
    
    all_good = True
    for name, value in checks.items():
        if value:
            if name == "Brevo API Key":
                masked = value[:20] + "..." + value[-10:]
                print(f"✅ {name}: {masked}")
            else:
                print(f"✅ {name}: {value}")
        else:
            print(f"❌ {name}: NOT SET")
            all_good = False
    
    print("\n" + "="*60)
    
    if all_good:
        print("✅ ALL CONFIGURATION CHECKS PASSED!")
        print("\nNext steps:")
        print("1. Start the server: python server.py")
        print("2. Navigate to: http://localhost:5000/forgot-password")
        print("3. Test the complete flow")
        return True
    else:
        print("❌ CONFIGURATION INCOMPLETE")
        print("\nMissing configuration:")
        if not os.getenv("BREVO_API_KEY"):
            print("- Add BREVO_API_KEY to .env")
            print("  Get it from: https://app.brevo.com → API Keys & SMTP")
        if not os.getenv("BREVO_SENDER_EMAIL"):
            print("- Add BREVO_SENDER_EMAIL to .env")
            print("  Verify it in: Brevo → Senders & identities")
        if not os.getenv("DATABASE_URL"):
            print("- Add DATABASE_URL to .env")
        return False
    
    print("="*60 + "\n")


def check_imports():
    """Check if all required packages are installed."""
    print("\n🔎 Checking Python packages...\n")
    
    required_packages = [
        ("Flask", "flask"),
        ("Brevo SDK", "sib_api_v3_sdk"),
        ("SQLAlchemy", "sqlalchemy"),
        ("bcrypt", "bcrypt"),
    ]
    
    all_good = True
    for display_name, package_name in required_packages:
        try:
            __import__(package_name)
            print(f"✅ {display_name}")
        except ImportError:
            print(f"❌ {display_name} - NOT INSTALLED")
            print(f"   Run: pip install {package_name}")
            all_good = False
    
    if all_good:
        print("\n✅ All packages installed!\n")
    else:
        print("\n❌ Some packages missing. Run: pip install -r requirements.txt\n")
    
    return all_good


def check_files():
    """Check if all required files exist."""
    print("\n📁 Checking required files...\n")
    
    required_files = [
        ("server.py", "Main server file"),
        ("templates/forgot_password.html", "Forgot password page"),
        ("init_database.py", "Database models"),
        ("db_helper.py", "Database helper"),
        ("requirements.txt", "Python dependencies"),
    ]
    
    all_good = True
    for filename, description in required_files:
        if os.path.exists(filename):
            print(f"✅ {filename}")
        else:
            print(f"❌ {filename} - NOT FOUND")
            all_good = False
    
    if all_good:
        print("\n✅ All files present!\n")
    else:
        print("\n❌ Some files missing. Check your installation.\n")
    
    return all_good


def main():
    """Run all checks."""
    print("\n")
    print("╔════════════════════════════════════════════════════════╗")
    print("║   PASSWORD RESET FEATURE - PRE-DEPLOYMENT CHECKLIST   ║")
    print("╚════════════════════════════════════════════════════════╝")
    
    results = []
    
    # Run all checks
    results.append(("Files", check_files()))
    results.append(("Imports", check_imports()))
    results.append(("Configuration", check_configuration()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60 + "\n")
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{check_name:20} {status}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL CHECKS PASSED - READY FOR DEPLOYMENT!")
        print("\nTo start the server:")
        print("  python server.py")
        print("\nTo test the feature:")
        print("  1. Open: http://localhost:5000/forgot-password")
        print("  2. Enter your email")
        print("  3. Check your inbox for the 6-digit code")
        print("  4. Follow the on-screen prompts")
    else:
        print("⚠️  SOME CHECKS FAILED - FIX ISSUES BEFORE DEPLOYING")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
