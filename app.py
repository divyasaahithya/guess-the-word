from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from collections import Counter
from functools import wraps
import random
import datetime
import os
import re

app = Flask(__name__)
app.secret_key = "supersecretkey"
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'game.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='player') # Roles: 'player' or 'admin'

class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(5), nullable=False, unique=True)

class UserGameStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    games_played = db.Column(db.Integer, default=0)

class Guess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_word = db.Column(db.String(5), nullable=False)
    guessed_word = db.Column(db.String(5), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    date = db.Column(db.Date, default=datetime.date.today)

def validate_username(username):
    return len(username) >= 5 and any(c.islower() for c in username) and any(c.isupper() for c in username)

def validate_password(password):
    return (len(password) >= 5 and re.search(r"[A-Za-z]", password)
            and re.search(r"\d", password)
            and re.search(r"[$%*@]", password))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if user.role != 'admin':
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def check_guess(guess, target):
    result, target_counts = [""] * 5, Counter(target)
    for i, char in enumerate(guess):
        if char == target[i]:
            result[i], target_counts[char] = "correct", target_counts[char] - 1
    for i, char in enumerate(guess):
        if result[i] == "":
            if char in target_counts and target_counts[char] > 0:
                result[i], target_counts[char] = "present", target_counts[char] - 1
            else:
                result[i] = "absent"
    return result

def seed_database():
    if Word.query.first() is None:
        print("Seeding words into the database...")
        words_to_seed = [
            "APPLE", "MONEY", "HOUSE", "TRAIN", "PLANE", "SWORD", "BOARD", "GREEN", "BRAIN", "WATER",
            "NIGHT", "LIGHT", "WORLD", "CLOUD", "MUSIC", "JOKER", "SMILE", "DREAM", "STARS", "HEART"
        ]
        for w in words_to_seed:
            db.session.add(Word(text=w))
        db.session.commit()
        print("Words seeded.")
    if User.query.filter_by(username='AdminUser').first() is None:
        print("Creating default admin user...")
        admin_user = User(
            username='AdminUser',
            password_hash=generate_password_hash('Admin@123', method='pbkdf2:sha256'),
            role='admin'
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created with username 'AdminUser' and password 'Admin@123'.")


@app.route("/")
def home():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'player')
        if not validate_username(username):
            flash("Username must be at least 5 characters with upper and lower case letters.", "danger")
        elif not validate_password(password):
            flash("Password must be at least 5 characters, with a letter, a number, and one of $, %, *, @.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
        elif role not in ['player', 'admin']:
            flash("Invalid role selected.", "danger")
        else:
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(username=username, password_hash=hashed_pw, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'], session['username'], session['role'] = user.id, user.username, user.role
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route("/start")
@login_required
def start_game():
    user_id, today = session['user_id'], datetime.date.today()
    stats = UserGameStats.query.filter_by(user_id=user_id, date=today).first()
    
    if not stats:
        stats = UserGameStats(user_id=user_id, date=today, games_played=0)
        db.session.add(stats)
        db.session.commit()

    if stats.games_played >= 3:
        flash("You have already played 3 times today. Please come back tomorrow!", "warning")
        return render_template("game.html", guesses=[], game_over=True, limit_reached=True)
    
    words = Word.query.all()
    if not words:
        flash("No words in the database to play with!", "danger")
        return redirect(url_for('home'))

    session["target_word"] = random.choice(words).text.upper()
    session["guesses"], session["game_over"] = [], False
    stats.games_played += 1
    db.session.commit()
    
    return redirect(url_for("play_game"))

@app.route("/play")
@login_required
def play_game():
    if "target_word" not in session:
        return redirect(url_for('start_game'))
    return render_template("game.html", guesses=session.get("guesses", []), game_over=session.get("game_over", False))

@app.route("/guess", methods=["POST"])
@login_required
def make_guess():
    if session.get("game_over"): return redirect(url_for("play_game"))
    
    guess_word = request.form["guess"].strip().upper()
    if len(guess_word) != 5 or not guess_word.isalpha():
        flash("Guess must be a 5-letter word.", "warning")
        return redirect(url_for("play_game"))

    target, guesses = session["target_word"], session.get("guesses", [])
    result = check_guess(guess_word, target)
    guesses.append((guess_word, result))
    is_correct = guess_word == target
    
    new_guess_entry = Guess(user_id=session['user_id'], target_word=target, guessed_word=guess_word, is_correct=is_correct, date=datetime.date.today())
    db.session.add(new_guess_entry)
    
    if is_correct:
        flash("🎉 Congratulations! You guessed the word!", "success")
        session["game_over"] = True
    elif len(guesses) >= 5:
        flash(f"Better luck next time! The word was {target}.", "danger")
        session["game_over"] = True
    
    session["guesses"] = guesses
    db.session.commit()
    return redirect(url_for("play_game"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route("/admin/daily_report", methods=['GET', 'POST'])
@admin_required
def daily_report():
    report_data = None
    selected_date_str = request.form.get('report_date', datetime.date.today().strftime('%Y-%m-%d'))
    selected_date = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        
    guesses_on_date = Guess.query.filter_by(date=selected_date).all()
    if guesses_on_date:
        users_played = len(set(g.user_id for g in guesses_on_date))
        correct_guesses = sum(1 for g in guesses_on_date if g.is_correct)
        report_data = {'date': selected_date, 'users_played': users_played, 'correct_guesses': correct_guesses}
    else:
        if request.method == 'POST':
            flash(f"No game data found for {selected_date.strftime('%Y-%m-%d')}.", "info")
            
    return render_template('daily_report.html', report_data=report_data, selected_date=selected_date_str)

@app.route("/admin/user_report", methods=['GET', 'POST'])
@admin_required
def user_report():
    users = User.query.filter_by(role='player').order_by(User.username).all()
    report_data = None
    selected_user_id = request.form.get('user_id')

    if request.method == 'POST' and selected_user_id:
        user = User.query.get(selected_user_id)
        if user:
            user_guesses = Guess.query.filter_by(user_id=selected_user_id).all()
            games_by_date = {}
            for g in user_guesses:
                date_str = g.date.strftime('%Y-%m-%d')
                if date_str not in games_by_date:
                    games_by_date[date_str] = {'words_tried': set(), 'correct_guesses': 0}
                games_by_date[date_str]['words_tried'].add(g.target_word)
                if g.is_correct:
                    games_by_date[date_str]['correct_guesses'] += 1
            
            sorted_stats = sorted(games_by_date.items(), key=lambda item: item[0], reverse=True)

            report_data = {
                'username': user.username,
                'stats': [{'date': d, 'tried': len(v['words_tried']), 'correct': v['correct_guesses']} for d, v in sorted_stats]
            }
            if not report_data['stats']:
                flash(f"No game data found for user '{user.username}'.", "info")
        else:
            flash("Selected user not found.", "danger")
            
    return render_template('user_report.html', users=users, report_data=report_data, selected_user_id=int(selected_user_id) if selected_user_id else None)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_database()
    app.run(debug=True)

