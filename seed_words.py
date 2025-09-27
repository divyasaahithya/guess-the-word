from app import app, db
from models import Word
with open('words.txt', 'r') as f:
    words = [line.strip().upper() for line in f if len(line.strip()) == 5]

with app.app_context():
    db.drop_all()
    db.create_all()
    for w in words:
        db.session.add(Word(text=w))
    db.session.commit()
    print("✅ Database seeded with words:", words)
