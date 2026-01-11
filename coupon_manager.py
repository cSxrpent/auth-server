import os
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base

Base = declarative_base()

class Coupon(Base):
    __tablename__ = 'coupons'
    
    code = Column(String(50), primary_key=True)
    discount_percent = Column(Integer, nullable=False)  # e.g., 10 for 10% off
    max_uses = Column(Integer, nullable=True)  # NULL = unlimited
    times_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(String(30), default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    expires_at = Column(String(30), nullable=True)  # Optional expiration date

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine))

# Create table if it doesn't exist
Base.metadata.create_all(engine)

@contextmanager
def get_db():
    """Context manager for database sessions"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

class CouponManager:
    """Manage coupon codes"""
    
    @staticmethod
    def create_coupon(code, discount_percent, max_uses=None, expires_at=None):
        """Create a new coupon"""
        try:
            with get_db() as db:
                existing = db.query(Coupon).filter_by(code=code.upper()).first()
                if existing:
                    return False, "Coupon code already exists"
                
                new_coupon = Coupon(
                    code=code.upper(),
                    discount_percent=discount_percent,
                    max_uses=max_uses,
                    expires_at=expires_at
                )
                db.add(new_coupon)
                return True, "Coupon created successfully"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def validate_coupon(code):
        """Validate a coupon and return discount info"""
        try:
            with get_db() as db:
                coupon = db.query(Coupon).filter_by(code=code.upper()).first()
                
                if not coupon:
                    return False, "Invalid coupon code", 0
                
                if not coupon.is_active:
                    return False, "Coupon is no longer active", 0
                
                if coupon.max_uses and coupon.times_used >= coupon.max_uses:
                    return False, "Coupon has reached max uses", 0
                
                if coupon.expires_at:
                    try:
                        expires = datetime.strptime(coupon.expires_at, "%Y-%m-%d %H:%M:%S")
                        if datetime.utcnow() > expires:
                            return False, "Coupon has expired", 0
                    except Exception:
                        pass
                
                return True, "Coupon valid", coupon.discount_percent
        except Exception as e:
            return False, str(e), 0
    
    @staticmethod
    def use_coupon(code):
        """Mark a coupon as used (increment usage counter)"""
        try:
            with get_db() as db:
                coupon = db.query(Coupon).filter_by(code=code.upper()).first()
                if coupon:
                    coupon.times_used += 1
                    return True
                return False
        except Exception as e:
            print(f"Error using coupon: {e}")
            return False
    
    @staticmethod
    def get_all_coupons():
        """Get all coupons for admin panel"""
        try:
            with get_db() as db:
                coupons = db.query(Coupon).all()
                return [
                    {
                        'code': c.code,
                        'discount_percent': c.discount_percent,
                        'max_uses': c.max_uses,
                        'times_used': c.times_used,
                        'is_active': c.is_active,
                        'created_at': c.created_at,
                        'expires_at': c.expires_at
                    }
                    for c in coupons
                ]
        except Exception as e:
            print(f"Error getting coupons: {e}")
            return []
    
    @staticmethod
    def toggle_coupon(code, is_active):
        """Enable/disable a coupon"""
        try:
            with get_db() as db:
                coupon = db.query(Coupon).filter_by(code=code.upper()).first()
                if coupon:
                    coupon.is_active = is_active
                    return True
                return False
        except Exception as e:
            print(f"Error toggling coupon: {e}")
            return False
    
    @staticmethod
    def delete_coupon(code):
        """Delete a coupon"""
        try:
            with get_db() as db:
                coupon = db.query(Coupon).filter_by(code=code.upper()).first()
                if coupon:
                    db.delete(coupon)
                    return True
                return False
        except Exception as e:
            print(f"Error deleting coupon: {e}")
            return False

coupon_manager = CouponManager()