"""
whatsapp.py
WhatsApp Click-to-Chat message generation for SN SOFTECH SOLUTIONS Resort
Management SaaS.

IMPORTANT (honesty about delivery status):
This module only builds a `wa.me` Click-to-Chat link with a pre-filled,
URL-encoded message. Opening that link does NOT guarantee the message
was sent - the staff member must press Send inside WhatsApp/WhatsApp Web.
We log every generated link as status 'Initiated' (or 'Opened' once the
UI confirms the link was clicked). We NEVER mark a message as delivered
or read from this module. A future integration with the official WhatsApp
Business API can update `whatsapp_logs.status` to 'API Delivered' without
touching any other module - the call sites here are the only integration
point that needs to change.
"""

import urllib.parse

from config import DEFAULT_COUNTRY_CODE
from database import get_connection, new_id
from utils import clean_mobile, currency, fmt_date, get_resort_profile


def build_whatsapp_url(mobile: str, message: str, country_code: str = None) -> str | None:
    """Returns a wa.me click-to-chat URL, or None if the mobile number is invalid."""
    digits = clean_mobile(mobile)
    if len(digits) < 7:
        return None

    cc = clean_mobile(country_code or DEFAULT_COUNTRY_CODE)
    # If the user already included the country code in the mobile field, don't double it.
    full_number = digits if digits.startswith(cc) and len(digits) > 10 else f"{cc}{digits}"

    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/{full_number}?text={encoded_message}"


def log_whatsapp_message(tenant_id, booking_id, guest_id, mobile_number, message_type, message_text,
                          sent_by, status="Initiated"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO whatsapp_logs
           (message_id, tenant_id, booking_id, guest_id, mobile_number, message_type, message_text, sent_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (new_id("WA-"), tenant_id, booking_id, guest_id, mobile_number, message_type, message_text, sent_by, status),
    )
    conn.commit()
    conn.close()


def booking_confirmation_message(tenant_id, booking: dict) -> str:
    profile = get_resort_profile(tenant_id)
    resort_name = profile.get("resort_name", "Our Resort")
    return (
        f"🏨 *{resort_name}*\n"
        f"*BOOKING CONFIRMATION*\n\n"
        f"Dear {booking.get('guest_name', '')},\n\n"
        f"Your resort booking has been confirmed successfully.\n\n"
        f"*Booking Details:*\n"
        f"Booking ID: {booking.get('booking_id', '')}\n"
        f"Guest Name: {booking.get('guest_name', '')}\n"
        f"Check-in: {fmt_date(booking.get('checkin_date'))} {booking.get('checkin_time', '')}\n"
        f"Check-out: {fmt_date(booking.get('checkout_date'))} {booking.get('checkout_time', '')}\n"
        f"Room No.: {booking.get('room_number', '')}\n"
        f"Room Type: {booking.get('room_type_name', '')}\n"
        f"Guests: {booking.get('adults', 0)} Adults, {booking.get('children', 0)} Children\n"
        f"No. of Nights: {booking.get('nights', 1)}\n"
        f"Room Charges: {currency(tenant_id, booking.get('room_tariff', 0))}\n"
        f"Discount: {currency(tenant_id, booking.get('discount', 0))}\n"
        f"Tax: {currency(tenant_id, booking.get('tax', 0))}\n"
        f"*Total Amount: {currency(tenant_id, booking.get('total_amount', 0))}*\n"
        f"Advance Paid: {currency(tenant_id, booking.get('advance_payment', 0))}\n"
        f"Balance: {currency(tenant_id, booking.get('balance', 0))}\n\n"
        f"Booking Status: CONFIRMED\n\n"
        f"Thank you for choosing {resort_name}.\n"
        f"📞 {profile.get('mobile', '')}\n"
        f"📍 {profile.get('address', '')}\n\n"
        f"_Powered by SN SOFTECH SOLUTIONS_"
    )


def payment_reminder_message(tenant_id, booking: dict) -> str:
    profile = get_resort_profile(tenant_id)
    resort_name = profile.get("resort_name", "Our Resort")
    return (
        f"Dear {booking.get('guest_name', '')},\n\n"
        f"This is a gentle reminder regarding your booking at {resort_name}.\n\n"
        f"Booking ID: {booking.get('booking_id', '')}\n"
        f"Total Amount: {currency(tenant_id, booking.get('total_amount', 0))}\n"
        f"Paid: {currency(tenant_id, booking.get('advance_payment', 0))}\n"
        f"Balance Due: {currency(tenant_id, booking.get('balance', 0))}\n\n"
        f"Please complete the pending payment at your convenience.\n\n"
        f"Thank you.\n{resort_name}\n{profile.get('mobile', '')}"
    )


def checkin_details_message(tenant_id, booking: dict) -> str:
    profile = get_resort_profile(tenant_id)
    resort_name = profile.get("resort_name", "Our Resort")
    return (
        f"🏨 *{resort_name}* - Check-In Confirmed\n\n"
        f"Dear {booking.get('guest_name', '')}, welcome!\n\n"
        f"Room Number: {booking.get('room_number', '')}\n"
        f"Room Type: {booking.get('room_type_name', '')}\n"
        f"Check-in: {fmt_date(booking.get('checkin_date'))} {booking.get('checkin_time', '')}\n"
        f"Check-out: {fmt_date(booking.get('checkout_date'))} {booking.get('checkout_time', '')}\n\n"
        f"📍 {profile.get('address', '')}\n"
        f"📞 {profile.get('mobile', '')}\n\n"
        f"We hope you enjoy your stay!\n_{resort_name}_"
    )


def final_bill_message(tenant_id, checkout: dict, invoice_number: str = "") -> str:
    profile = get_resort_profile(tenant_id)
    resort_name = profile.get("resort_name", "Our Resort")
    return (
        f"🏨 *{resort_name}* - Final Bill\n\n"
        f"Dear {checkout.get('guest_name', '')},\n\n"
        f"Booking ID: {checkout.get('booking_id', '')}\n"
        f"Invoice No.: {invoice_number}\n"
        f"Room: {checkout.get('room_number', '')}\n"
        f"Room Charges: {currency(tenant_id, checkout.get('room_charges', 0))}\n"
        f"Restaurant Charges: {currency(tenant_id, checkout.get('restaurant_charges', 0))}\n"
        f"Other Charges: {currency(tenant_id, checkout.get('other_charges', 0))}\n"
        f"Discount: {currency(tenant_id, checkout.get('discount', 0))}\n"
        f"Tax: {currency(tenant_id, checkout.get('tax', 0))}\n"
        f"*Total: {currency(tenant_id, checkout.get('total_amount', 0))}*\n"
        f"Paid: {currency(tenant_id, checkout.get('advance_paid', 0))}\n"
        f"Balance: {currency(tenant_id, checkout.get('balance', 0))}\n\n"
        f"Thank you for staying with us!\n_{resort_name}_"
    )


def payment_receipt_message(tenant_id, payment: dict, guest_name: str = "") -> str:
    profile = get_resort_profile(tenant_id)
    resort_name = profile.get("resort_name", "Our Resort")
    return (
        f"🏨 *{resort_name}* - Payment Receipt\n\n"
        f"Dear {guest_name},\n\n"
        f"Booking ID: {payment.get('booking_id', '')}\n"
        f"Amount Received: {currency(tenant_id, payment.get('amount', 0))}\n"
        f"Payment Mode: {payment.get('payment_mode', '')}\n"
        f"Date: {fmt_date(payment.get('payment_date'))}\n\n"
        f"Thank you!\n_{resort_name}_"
    )


TEMPLATE_VARIABLES = [
    "{guest_name}", "{booking_id}", "{room_no}", "{checkin_date}", "{checkout_date}",
    "{total_amount}", "{paid_amount}", "{balance}", "{resort_name}", "{resort_mobile}",
]


def render_custom_template(tenant_id, template_text: str, data: dict) -> str:
    profile = get_resort_profile(tenant_id)
    mapping = {
        "{guest_name}": data.get("guest_name", ""),
        "{booking_id}": data.get("booking_id", ""),
        "{room_no}": data.get("room_number", ""),
        "{checkin_date}": fmt_date(data.get("checkin_date", "")),
        "{checkout_date}": fmt_date(data.get("checkout_date", "")),
        "{total_amount}": currency(tenant_id, data.get("total_amount", 0)),
        "{paid_amount}": currency(tenant_id, data.get("advance_payment", 0)),
        "{balance}": currency(tenant_id, data.get("balance", 0)),
        "{resort_name}": profile.get("resort_name", ""),
        "{resort_mobile}": profile.get("mobile", ""),
    }
    text = template_text
    for key, value in mapping.items():
        text = text.replace(key, str(value))
    return text
