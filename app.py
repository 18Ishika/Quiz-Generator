from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import os
import re
from dotenv import load_dotenv
from generator import QuestionGenerator

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(16))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    share_link = db.Column(db.String(50), unique=True, nullable=False)
    questions = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy=True, cascade='all, delete-orphan')

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    student_email = db.Column(db.String(100))
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    answers = db.Column(db.JSON, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

# Initialize database
with app.app_context():
    db.create_all()

def normalize_answer(answer):
    """Normalize answer for comparison by removing extra whitespace and converting to lowercase"""
    if not answer:
        return ''
    # Convert to string, strip, and lowercase
    answer = str(answer).strip().lower()
    # Replace multiple spaces with single space
    answer = re.sub(r'\s+', ' ', answer)
    return answer

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create-quiz', methods=['GET', 'POST'])
def create_quiz():
    if request.method == 'POST':
        topic = request.form.get('topic')
        difficulty = request.form.get('difficulty', 'medium')
        num_questions = int(request.form.get('num_questions', 5))
        title = request.form.get('title', f"{topic} Quiz")
        
        try:
            generator = QuestionGenerator()
            questions = []
            
            for _ in range(num_questions):
                q = generator.generate_mcq(topic, difficulty.lower())
                questions.append({
                    'question': q.question,
                    'options': q.options,
                    'correct_answer': q.correct_answer
                })
            
            # Generate unique share link
            share_link = secrets.token_urlsafe(8)
            
            # Save quiz to database
            quiz = Quiz(
                title=title,
                topic=topic,
                difficulty=difficulty,
                share_link=share_link,
                questions=questions
            )
            db.session.add(quiz)
            db.session.commit()
            
            return redirect(url_for('quiz_created', share_link=share_link))
        
        except Exception as e:
            return render_template('create_quiz.html', error=str(e))
    
    return render_template('create_quiz.html')

@app.route('/quiz-created/<share_link>')
def quiz_created(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    quiz_url = request.host_url + 'quiz/' + share_link
    return render_template('quiz_created.html', quiz=quiz, quiz_url=quiz_url)

@app.route('/quiz/<share_link>', methods=['GET', 'POST'])
def take_quiz(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        student_email = request.form.get('student_email', '')
        
        # Calculate score
        score = 0
        answers = []
        
        for i, question in enumerate(quiz.questions):
            user_answer = request.form.get(f'question_{i}')
            correct_answer = question['correct_answer']
            
            # Normalize both answers for comparison
            user_normalized = normalize_answer(user_answer)
            correct_normalized = normalize_answer(correct_answer)
            
            # Compare normalized versions
            is_correct = user_normalized == correct_normalized
            
            if is_correct:
                score += 1
            
            # Debug output (optional - remove in production)
            if app.debug:
                print(f"Question {i+1}:")
                print(f"  User: '{user_answer}' -> '{user_normalized}'")
                print(f"  Correct: '{correct_answer}' -> '{correct_normalized}'")
                print(f"  Match: {is_correct}")
            
            answers.append({
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct
            })
        
        # Save attempt
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_name=student_name,
            student_email=student_email,
            score=score,
            total_questions=len(quiz.questions),
            answers=answers
        )
        db.session.add(attempt)
        db.session.commit()
        
        if app.debug:
            print(f"Final score: {score}/{len(quiz.questions)}")
            print(f"Redirecting to results for attempt #{attempt.id}")
        
        return redirect(url_for('quiz_results', attempt_id=attempt.id))
    
    return render_template('take_quiz.html', quiz=quiz)

@app.route('/results/<int:attempt_id>')
def quiz_results(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    percentage = (attempt.score / attempt.total_questions) * 100
    return render_template('results.html', attempt=attempt, percentage=percentage)

@app.route('/my-quizzes')
def my_quizzes():
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    return render_template('my_quizzes.html', quizzes=quizzes)

@app.route('/quiz-report/<share_link>')
def quiz_report(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).order_by(QuizAttempt.completed_at.desc()).all()
    
    # Calculate statistics
    total_attempts = len(attempts)
    if total_attempts > 0:
        avg_score = sum(a.score for a in attempts) / total_attempts
        avg_percentage = (avg_score / len(quiz.questions)) * 100
    else:
        avg_score = 0
        avg_percentage = 0
    
    return render_template('quiz_report.html', 
                         quiz=quiz, 
                         attempts=attempts, 
                         total_attempts=total_attempts,
                         avg_percentage=avg_percentage)

@app.route('/delete-quiz/<int:quiz_id>', methods=['POST'])
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for('my_quizzes'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)