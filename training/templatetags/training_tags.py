import json
from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe
from ..translations import get_translation

register = template.Library()

@register.simple_tag
def t(key):
    """
    Template tag to get translation for a key.
    Usage: {% t "courses" %}
    """
    return get_translation(key)

@register.filter
def translate(value):
    """
    Template filter to translate a value.
    Usage: {{ "courses"|translate }}
    """
    return get_translation(value)

@register.simple_tag
def url_replace(request, field, value):
    """
    Template tag to replace a GET parameter in the current URL.
    Usage: {% url_replace request 'page' 2 %}
    """
    query_dict = request.GET.copy()
    query_dict[field] = value
    return query_dict.urlencode()

@register.filter
def lessons_to_json(modules):
    """
    Template filter to convert a queryset of modules and their lessons to a JSON string.
    """
    modules_list = []
    for module in modules:
        lessons_list = list(module.lessons.values('title', 'duration'))
        modules_list.append({
            'title': module.title,
            'lessons': lessons_list
        })
    return json.dumps(modules_list, cls=DjangoJSONEncoder)

@register.filter
def split(value, delimiter=','):
    """
    Template filter to split a string by delimiter.
    Usage: {{ "a,b,c"|split:"," }}
    """
    # Simple case - just split by delimiter
    return value.split(delimiter)

@register.filter
def equals(value, arg):
    """
    Template filter to check if a value equals another.
    Usage: {{ value|equals:"expected" }}
    """
    return value == arg

@register.simple_tag
def language_chips():
    """
    Template tag to generate language chips HTML.
    Usage: {% language_chips %}
    """
    languages = [
        {'code': 'sw', 'label': 'Kiswahili', 'flag': 'tz'},
        {'code': 'en', 'label': 'English', 'flag': 'gb'},
        {'code': 'suk', 'label': 'Kisukuma', 'flag': 'tz'},
        {'code': 'mas', 'label': 'Kimaasai', 'flag': 'tz'},
        {'code': 'hay', 'label': 'Kihaya', 'flag': 'tz'}
    ]
    
    html = ''
    for lang in languages:
        html += f'''
        <button class="lang-chip flex items-center gap-1 px-3 py-1 text-xs rounded-full bg-gray-100 text-gray-900 hover:bg-gray-200"
                data-lang="{lang['code']}">
          <img src="https://flagcdn.com/{lang['flag']}.svg" class="w-4 h-4 rounded-full" alt="{lang['label']}">
          <span>{lang['label']}</span>
        </button>
        '''
    
    return mark_safe(html)
