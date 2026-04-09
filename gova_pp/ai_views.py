import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import FarmerMessage, GovernmentReply
import os
from openai import OpenAI

logger = logging.getLogger('gova_pp')

@login_required
@require_http_methods(["POST"])
def ai_chat(request):
    """
    Handle AI assistant chat requests
    Provides context-aware responses based on conversation history
    """
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        thread_id = data.get('thread_id')
        
        if not question:
            return JsonResponse({'error': 'Question is required'}, status=400)
        
        # Get conversation context
        context = get_conversation_context(thread_id)
        
        # Generate AI response
        ai_response = generate_ai_response(question, context)
        
        return JsonResponse({
            'success': True,
            'response': ai_response,
            'timestamp': 'now'
        })
        
    except Exception as e:
        logger.error(f"Error in AI chat: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def suggest_response(request, thread_id):
    """
    Generate suggested responses based on farmer's message
    """
    try:
        thread = FarmerMessage.objects.get(id=thread_id)
        
        # Analyze the message and generate suggestions
        suggestions = generate_response_suggestions(thread)
        
        return JsonResponse({
            'success': True,
            'suggestions': suggestions
        })
        
    except FarmerMessage.DoesNotExist:
        return JsonResponse({'error': 'Thread not found'}, status=404)
    except Exception as e:
        logger.error(f"Error generating suggestions: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def analyze_conversation(request, thread_id):
    """
    Analyze conversation and provide insights
    """
    try:
        thread = FarmerMessage.objects.get(id=thread_id)
        replies = GovernmentReply.objects.filter(message=thread).order_by('created_at')
        
        analysis = {
            'summary': f"Conversation about {thread.subject}",
            'status': thread.get_status_display(),
            'priority': thread.get_priority_display(),
            'total_messages': replies.count() + 1,
            'response_time': 'Quick' if replies.exists() else 'Pending',
            'sentiment': 'Neutral',  # Placeholder for sentiment analysis
            'key_topics': extract_key_topics(thread, replies),
            'recommended_actions': generate_recommended_actions(thread)
        }
        
        return JsonResponse({
            'success': True,
            'analysis': analysis
        })
        
    except FarmerMessage.DoesNotExist:
        return JsonResponse({'error': 'Thread not found'}, status=404)
    except Exception as e:
        logger.error(f"Error analyzing conversation: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def get_conversation_context(thread_id):
    """
    Retrieve conversation context for AI processing
    """
    try:
        thread = FarmerMessage.objects.get(id=thread_id)
        replies = GovernmentReply.objects.filter(message=thread).order_by('created_at')
        
        context = {
            'farmer_name': thread.farmer_name,
            'farmer_location': thread.farmer_location,
            'subject': thread.subject,
            'original_message': thread.message,
            'status': thread.status,
            'priority': thread.priority,
            'conversation_history': [
                {
                    'sender': 'farmer',
                    'text': thread.message,
                    'timestamp': thread.created_at.isoformat()
                }
            ]
        }
        
        # Add replies to history
        for reply in replies:
            context['conversation_history'].append({
                'sender': 'government',
                'text': reply.reply_text,
                'timestamp': reply.created_at.isoformat()
            })
        
        return context
        
    except FarmerMessage.DoesNotExist:
        return {}


def generate_ai_response(question, context):
    """
    Generate AI response based on question and context using OpenAI
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    
    if not api_key:
        return "I'm sorry, but the OpenAI API key is not configured. Please contact the administrator."

    try:
        client = OpenAI(api_key=api_key)
        
        # Construct system prompt with context
        system_prompt = f"""You are an intelligent agricultural assistant for the Tanzanian government's Mkulima Smart platform. 
        Your goal is to assist government officers in supporting farmers.
        
        Context about the current conversation:
        - Farmer Name: {context.get('farmer_name', 'Unknown')}
        - Location: {context.get('farmer_location', 'Unknown')}
        - Subject: {context.get('subject', 'General Inquiry')}
        - Status: {context.get('status', 'Unknown')}
        
        Please provide helpful, accurate, and professional advice. 
        If the query is about specific crops, pests, or weather, provide detailed agricultural guidance.
        Keep responses concise and easy to read.
        """

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Add recent conversation history for context (last 5 messages)
        history = context.get('conversation_history', [])
        for msg in history[-5:]: 
            role = "user" if msg['sender'] == 'farmer' else "assistant"
            messages.append({"role": role, "content": msg['text']})
            
        # Add the current question
        messages.append({"role": "user", "content": question})

        response = client.chat.completions.create(
            model="gpt-4", # Use gpt-4 for better reasoning
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI API Error: {str(e)}")
        return "I apologize, but I'm having trouble connecting to my AI brain right now. Please try again later."


def generate_response_suggestions(thread):
    """
    Generate suggested responses for the thread using OpenAI
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    
    # Fallback to static suggestions if no API key
    if not api_key:
        return [
            {
                'title': 'Acknowledge Receipt',
                'text': f'Dear {thread.farmer_name}, thank you for contacting us. We have received your message and will respond within 24 hours.'
            },
            {
                'title': 'Request More Information',
                'text': f'Dear {thread.farmer_name}, to better assist you, could you please provide more details about your location and the specific challenges you\'re facing?'
            },
            {
                'title': 'Provide Resources',
                'text': f'Dear {thread.farmer_name}, based on your inquiry, I recommend visiting our agricultural extension office. Our team can provide on-site support.'
            }
        ]

    try:
        client = OpenAI(api_key=api_key)
        
        prompt = f"""Generate 3 distinct, professional response suggestions for a government officer replying to a farmer.
        
        Farmer Name: {thread.farmer_name}
        Message: "{thread.message}"
        Subject: {thread.subject}
        
        Format the output as a JSON array of objects with 'title' and 'text' keys.
        Example:
        [
            {{"title": "Acknowledge", "text": "Dear..."}},
            {{"title": "Ask Details", "text": "Could you..."}}
        ]
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant generating response drafts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Handle different JSON structures (sometimes it returns { "suggestions": [...] })
        if 'suggestions' in data:
            return data['suggestions']
        elif isinstance(data, list):
            return data
        else:
            # Fallback if structure is unexpected
            return list(data.values())[0] if data else []

    except Exception as e:
        logger.error(f"OpenAI Suggestion Error: {str(e)}")
        # Return fallback suggestions on error
        return [
            {
                'title': 'Acknowledge Receipt',
                'text': f'Dear {thread.farmer_name}, thank you for contacting us. We have received your message and will respond within 24 hours.'
            },
            {
                'title': 'Request More Information',
                'text': f'Dear {thread.farmer_name}, to better assist you, could you please provide more details about your location and the specific challenges you\'re facing?'
            }
        ]


def extract_key_topics(thread, replies):
    """
    Extract key topics from conversation (placeholder for NLP)
    """
    # Simple keyword extraction (replace with actual NLP)
    all_text = thread.message + ' ' + ' '.join([r.reply_text for r in replies])
    
    keywords = ['crops', 'irrigation', 'fertilizer', 'pests', 'weather', 'harvest']
    found_topics = [k for k in keywords if k in all_text.lower()]
    
    return found_topics if found_topics else ['general inquiry']


def generate_recommended_actions(thread):
    """
    Generate recommended actions based on thread status and priority
    """
    actions = []
    
    if thread.status == 'new':
        actions.append('Send initial response to farmer')
    
    if thread.priority == 'high':
        actions.append('Escalate to senior officer')
        actions.append('Schedule urgent site visit')
    
    if not thread.assigned_to:
        actions.append('Assign to available officer')
    
    actions.append('Update case status')
    actions.append('Set follow-up reminder')
    
    return actions


@csrf_exempt
@require_http_methods(["POST"])
def analyze_image(request):
    """
    Analyze an image using OpenAI's vision capabilities
    Returns agricultural insights about the image
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        image_url = data.get('image_url', '').strip()
        thread_id = data.get('thread_id')
        media_id = data.get('media_id')
        
        if not image_url:
            return JsonResponse({'error': 'Image URL is required'}, status=400)
        
        # Get conversation context if thread_id provided
        context = {}
        if thread_id:
            context = get_conversation_context(thread_id)
        
        # Analyze the image using OpenAI Vision
        analysis = analyze_image_with_ai(image_url, context)
        
        return JsonResponse({
            'success': True,
            'analysis': analysis,
            'media_id': media_id,
            'timestamp': 'now'
        })
        
    except Exception as e:
        logger.error(f"Error in image analysis: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def analyze_image_with_ai(image_url, context=None):
    """
    Analyze an image using OpenAI's GPT-4 Vision
    """
    import base64
    import requests
    from urllib.parse import urlparse
    
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    
    if not api_key:
        return "I'm sorry, but the OpenAI API key is not configured. Please contact the administrator to enable image analysis."

    try:
        client = OpenAI(api_key=api_key)
        
        # Convert image to base64 if it's a local URL
        image_data = None
        parsed_url = urlparse(image_url)
        
        # Check if it's a local/private URL that OpenAI can't access
        is_local = any(x in parsed_url.netloc for x in ['localhost', '127.0.0.1', '192.168.', '10.', '172.'])
        
        if is_local or image_url.startswith('/media/'):
            # Try to read the file directly from disk
            if '/media/' in image_url:
                # Extract the path after /media/
                media_path = image_url.split('/media/')[-1]
                file_path = os.path.join(settings.MEDIA_ROOT, media_path)
                
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        image_bytes = f.read()
                    
                    # Determine mime type
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if not mime_type:
                        mime_type = 'image/jpeg'
                    
                    image_data = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                    logger.info(f"Loaded image from disk: {file_path}")
                else:
                    logger.error(f"Image file not found: {file_path}")
                    return f"Image file not found on server."
        
        # Build context string
        context_info = ""
        if context:
            context_info = f"""
            Context about the farmer:
            - Farmer Name: {context.get('farmer_name', 'Unknown')}
            - Location: {context.get('farmer_location', 'Unknown')}
            - Subject: {context.get('subject', 'General Inquiry')}
            """
        
        system_prompt = f"""You are an expert agricultural analyst for the Tanzanian government's Mkulima Smart platform.
        Analyze the provided image and give detailed, actionable insights.
        
        {context_info}
        
        Focus on:
        1. **Identification**: What is shown in the image (crop type, pest, disease, soil condition, etc.)
        2. **Assessment**: Current health/condition assessment
        3. **Diagnosis**: If there are problems, identify them specifically
        4. **Recommendations**: Provide practical, actionable advice for the farmer
        5. **Urgency**: Rate the urgency (Low/Medium/High) if action is needed
        
        Format your response with clear sections using markdown.
        Be specific and practical - remember this is for Tanzanian farmers.
        """

        # Use base64 data if available, otherwise use URL
        image_content = {"url": image_data if image_data else image_url}
        if image_data:
            image_content["detail"] = "high"
        
        response = client.chat.completions.create(
            model="gpt-4o",  # GPT-4 with vision capabilities
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please analyze this image from a farmer and provide agricultural insights:"
                        },
                        {
                            "type": "image_url",
                            "image_url": image_content
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI Vision API Error: {str(e)}")
        return f"I apologize, but I couldn't analyze this image. Error: {str(e)}"
