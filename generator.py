import os
import time
import json
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel, field_validator, Field, ValidationError
from typing import List
import re

load_dotenv()

class MCQQuestion(BaseModel):   
    question: str = Field(description="The question text")
    options: List[str] = Field(description="List of 4 possible answers")
    correct_answer: str = Field(description="The correct answer from the options")

    @field_validator("question", mode="before")
    @classmethod
    def clean_question(cls, v):
        if isinstance(v, dict):
            return v.get('description', str(v))
        return str(v).strip()
    
    @field_validator("options", mode="before")
    @classmethod
    def clean_options(cls, v):
        if isinstance(v, list):
            return [str(opt).strip() for opt in v if opt]
        return v
    
    @field_validator("correct_answer", mode="before")
    @classmethod
    def clean_correct_answer(cls, v):
        return str(v).strip()

class QuestionGenerator:
    def __init__(self):
        """Initialize the generator with robust error handling"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        
        try:
            genai.configure(api_key=api_key)
            
            self.model = genai.GenerativeModel(
                model_name="models/gemini-2.5-flash",  # or "models/gemini-2.5-pro"
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
            )


            # Test the model
            test_response = self.model.generate_content("Return JSON: {\"test\": \"ok\"}")
            test_text = self._get_response_text(test_response)
            if test_text:
                print(f"✓ AI Model initialized successfully")
            else:
                raise ValueError("Model test failed")
            
        except Exception as e:
            raise ValueError(f"Failed to initialize AI model: {str(e)}")
        
        self.last_call_time = 0
        self.min_call_interval = 2.0
    
    def _get_response_text(self, response) -> str:
        """Safely extract text from Gemini response"""
        try:
            # Try the simple accessor first
            if hasattr(response, 'text') and response.text:
                return response.text
        except:
            pass
        
        try:
            # Try accessing parts
            if hasattr(response, 'parts') and response.parts:
                return ''.join(part.text for part in response.parts if hasattr(part, 'text'))
        except:
            pass
        
        try:
            # Try the full path
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    return ''.join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
        except:
            pass
        
        return ""
    
    def _rate_limit(self):
        """Ensure we don't overwhelm the API with rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_call_time
        if time_since_last < self.min_call_interval:
            sleep_time = self.min_call_interval - time_since_last
            time.sleep(sleep_time)
        self.last_call_time = time.time()
    
    def _extract_json(self, content: str) -> dict:
        """Extract JSON from various response formats with improved handling"""
        if not content or not content.strip():
            raise ValueError("Empty content received")
        
        content = content.strip()
        
        # Remove markdown code blocks
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()
        
        # Try to find JSON object boundaries
        # Look for the first { and last }
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError(f"No JSON object found in response: {content[:100]}")
        
        json_str = content[start_idx:end_idx + 1]
        
        # Clean up any control characters that might break JSON parsing
        json_str = json_str.replace('\n', ' ').replace('\r', ' ')
        json_str = re.sub(r'\s+', ' ', json_str)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # If direct parsing fails, try to fix common issues
            # Fix unescaped quotes in strings
            try:
                # This is a basic fix - might need more sophisticated handling
                fixed_json = json_str.replace('\\"', '"')
                return json.loads(fixed_json)
            except:
                raise ValueError(f"JSON parsing failed: {str(e)}. Content: {json_str[:200]}")
    
    def generate_mcq(self, topic: str, difficulty: str = 'medium') -> MCQQuestion:
        """Generate MCQ with robust error handling and validation"""
        if not topic or not topic.strip():
            raise ValueError("Topic cannot be empty")
        
        difficulty = difficulty.lower()
        if difficulty not in ['easy', 'medium', 'hard']:
            difficulty = 'medium'
        
        self._rate_limit()
        
        # Simplified prompt that emphasizes JSON-only output
        prompt = (
            f"Create a {difficulty} multiple-choice question about {topic}.\n\n"
            "Output ONLY a valid JSON object with no additional text, markdown, or explanations.\n"
            "Use this EXACT structure:\n\n"
            "{\n"
            '  "question": "Your question text here?",\n'
            '  "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            '  "correct_answer": "Option A"\n'
            "}\n\n"
            "Requirements:\n"
            "- Provide exactly 4 distinct options\n"
            "- The correct_answer must match one of the options exactly\n"
            "- Keep all text simple and avoid special characters\n"
            "- Do not include any text before or after the JSON\n"
        )

        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                # Generate response using Gemini
                response = self.model.generate_content(prompt)
                
                # Get response text using safe accessor
                response_text = self._get_response_text(response)
                
                if not response_text:
                    raise ValueError("Empty response from AI")
                
                # Extract and parse JSON
                json_data = self._extract_json(response_text)
                
                # Validate JSON structure
                required_keys = ['question', 'options', 'correct_answer']
                if not all(key in json_data for key in required_keys):
                    missing = [k for k in required_keys if k not in json_data]
                    raise ValueError(f"Missing required fields: {missing}")
                
                # Create and validate MCQ object
                parsed_response = MCQQuestion(**json_data)
                
                # Additional validation
                if len(parsed_response.options) != 4:
                    raise ValueError(f"Expected 4 options, got {len(parsed_response.options)}")
                
                # Check if correct answer is in options (case-insensitive match)
                correct_lower = parsed_response.correct_answer.lower().strip()
                option_match = None
                
                for option in parsed_response.options:
                    if option.lower().strip() == correct_lower:
                        option_match = option
                        break
                
                if not option_match:
                    raise ValueError(f"Correct answer '{parsed_response.correct_answer}' not found in options")
                
                # Use the matched option for consistency
                parsed_response.correct_answer = option_match
                
                # Check for duplicate options
                unique_options = set(opt.lower().strip() for opt in parsed_response.options)
                if len(unique_options) != 4:
                    raise ValueError("Duplicate options found")
                
                # Success!
                print(f"✓ Generated question for '{topic}' (attempt {attempt + 1})")
                return parsed_response
                
            except json.JSONDecodeError as e:
                last_error = f"JSON parsing error: {str(e)}"
                print(f"✗ Attempt {attempt + 1} failed: {last_error}")
                
            except ValidationError as e:
                last_error = f"Validation error: {str(e)}"
                print(f"✗ Attempt {attempt + 1} failed: {last_error}")
                
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                print(f"✗ Attempt {attempt + 1} failed: {last_error}")
            
            # Wait before retry (exponential backoff)
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 2.0
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        # All attempts failed, use fallback
        print(f"⚠ All attempts failed. Using fallback question. Last error: {last_error}")
        return self._create_fallback_mcq(topic, difficulty)

    def _create_fallback_mcq(self, topic: str, difficulty: str) -> MCQQuestion:
        """Create a reasonable fallback MCQ when API fails"""
        difficulty_desc = {
            'easy': 'basic',
            'medium': 'intermediate',
            'hard': 'advanced'
        }.get(difficulty, 'general')
        
        return MCQQuestion(
            question=f"Which of the following best describes a {difficulty_desc} aspect of {topic}?",
            options=[
                f"Fundamental concepts of {topic}",
                f"Advanced theories in mathematics",
                f"Historical events in ancient Rome",
                f"Chemical properties of water"
            ],
            correct_answer=f"Fundamental concepts of {topic}"
        )

    def test_connection(self) -> bool:
        """Test if the AI connection is working"""
        try:
            test_question = self.generate_mcq("Python programming", "easy")
            return test_question is not None
        except Exception as e:
            print(f"Connection test failed: {str(e)}")
            return False

    @staticmethod
    def list_available_models():
        """Helper method to list all available models"""
        try:
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("GOOGLE_API_KEY not found")
                return []
            
            genai.configure(api_key=api_key)
            print("\nAvailable Gemini models that support generateContent:")
            available_models = []
            
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    print(f"  ✓ {model.name}")
                    available_models.append(model.name)
            
            if not available_models:
                print("  ✗ No models found that support generateContent")
            
            return available_models
            
        except Exception as e:
            print(f"Error listing models: {str(e)}")
            return []


# Test function for development
if __name__ == "__main__":
    print("Testing Question Generator...\n")
    
    # First, list available models to help with debugging
    print("=" * 60)
    available = QuestionGenerator.list_available_models()
    print("=" * 60)
    
    if not available:
        print("\n⚠ Warning: No models found. Please check your API key.")
        print("   You can get an API key from: https://makersuite.google.com/app/apikey")
        exit(1)
    
    try:
        generator = QuestionGenerator()
        print("\n✓ Generator initialized successfully\n")
        
        # Test with different topics
        test_cases = [
            ("Python programming", "easy"),
            ("World War II", "medium"),
            ("Quantum Physics", "hard")
        ]
        
        for topic, difficulty in test_cases:
            print(f"\nGenerating {difficulty} question about '{topic}'...")
            question = generator.generate_mcq(topic, difficulty)
            
            print(f"\nQuestion: {question.question}")
            print("Options:")
            for i, option in enumerate(question.options, 1):
                marker = "✓" if option == question.correct_answer else " "
                print(f"  {i}. [{marker}] {option}")
            print(f"Correct Answer: {question.correct_answer}")
            print("-" * 60)
        
        print("\n✓ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")