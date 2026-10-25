"""Custom template tags and filters untuk seluruh aplikasi."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Ambil nilai dari dict menggunakan key. Pakai: {{ dict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
