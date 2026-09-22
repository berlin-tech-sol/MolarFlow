import json
import datetime
import logging
import functools
import werkzeug.wrappers
from .common import valid_response, invalid_response
from odoo import http
# from models import 
# from odoo.models.
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

def validate_token(func):
    @functools.wraps(func)
    def wrap(self, *args, **kwargs):
        access_token = request.httprequest.headers.get("access_token")
        if not access_token:
            return invalid_response("access_token_not_found", "missing access token in request header", 401)
        access_token_data = request.env["api.access_token"].sudo().search([("token", "=", access_token)],
                                                                          order="id DESC", limit=1)

        if access_token_data.find_or_create_token(user_id=access_token_data.user_id.id) != access_token:
            return invalid_response("access_token", "token seems to have expired or invalid", 401)

        request.session.uid = access_token_data.user_id.id
        request.uid = access_token_data.user_id.id
        return func(self, *args, **kwargs)

    return wrap



class AcessToken(http.Controller):
    @http.route("/api/login", methods=["GET"], type="http", auth="none", csrf=False)
    def api_login(self, **post):
        """The token URL to be used for getting the access_token:

        Args:
            **post must contain login and password.
        Returns:

            returns https response code 404 if failed error message in the body in json format
            and status code 202 if successful with the access_token.
        Example:
           import requests

           headers = {'content-type': 'text/plain', 'charset':'utf-8'}

           data = {
               'login': 'admin',
               'password': 'admin',
               'db': 'galago.ng'
            }
           base_url = 'http://odoo.ng'
           eq = requests.post(
               '{}/api/auth/token'.format(base_url), data=data, headers=headers)
           content = json.loads(req.content.decode('utf-8'))
           headers.update(access-token=content.get('access_token'))

        If you would like to use body to send the data you can do the following:
            payload = request.httprequest.data.decode()
            payload = json.loads(payload)
            db, username, password = (
                payload.get("db"),
                payload.get("login"),
                payload.get("password"),
            )
        """

        params = ["db", "login", "password"]
        params = {key: post.get(key) for key in params if post.get(key)}
        db, username, password = (params.get("db"), post.get("login"), post.get("password"))
        _credentials_includes_in_body = all([db, username, password])
        if not _credentials_includes_in_body:
            headers = request.httprequest.headers
            db = headers.get("db")
            username = headers.get("login")
            password = headers.get("password")
            _credentials_includes_in_headers = all([db, username, password])
            if not _credentials_includes_in_headers:
                # Empty 'db' or 'username' or 'password:
                return (werkzeug.wrappers.Response(status=403, content_type="application/json; charset=utf-8", response=json.dumps(
            {"type": "missing error", "message": "either of the following are missing [db, username,password]",}, default=datetime.datetime.isoformat,),
                    ))
            
        # Login in odoo database:
        try:
            request.session.authenticate(db, username, password)
        except AccessError as aee:
            return (werkzeug.wrappers.Response(status=401, content_type="application/json; charset=utf-8", response=json.dumps({"type": "Access Error", "message": (str("Error: %s" % aee.name)),}, default=datetime.datetime.isoformat,),))
        except AccessDenied as ade:
            return (werkzeug.wrappers.Response(status=401, content_type="application/json; charset=utf-8", response=json.dumps({"type": "Access Denied", "message": "Login, password or db invalid",}, default=datetime.datetime.isoformat,),))
        except Exception as e:
            # Invalid database:
            info = "The database name is not valid {}".format((e))
            error = "invalid_database"
            _logger.error(info)
            return invalid_response("wrong database name", error, 403)

        uid = request.session.uid
        # odoo login failed:
        if not uid:
            info = "authentication failed"
            error = "authentication failed"
            _logger.error(info)
            return invalid_response(401, error, info)

        # Generate tokens
        access_token = request.env["api.access_token"].find_or_create_token(user_id=uid, create=True)
        # Successful response:
        clinic_appointments = request.env["patient.appointment"].search_read([('start', '>=', datetime.datetime.now())])
        print(request.env["patient.appointment"].search_read([('start', '>=', datetime.datetime.now())]))
        print(request.session)
        print(request.env)
        return werkzeug.wrappers.Response(
            status=200,
            content_type="application/json; charset=utf-8",
            headers=[("Cache-Control", "no-store"), ("Pragma", "no-cache")],
            response=json.dumps(
                {
                    "uid": uid,
                    "user_context": request.session.get_context() if uid else {},
                    "company_id": request.env.user.company_id.id if uid else None,
                    "company_ids": request.env.user.company_ids.ids if uid else None,
                    "partner_id": request.env.user.partner_id.id,
                    "access_token": access_token,
                    "company_name": request.env.user.company_name,
                    "country": request.env.user.country_id.name,
                    "contact_address": request.env.user.contact_address,
                    "clinic appointments": str(clinic_appointments),
                    "request.env": [i for i in request.env], # request.env contains all installed modules 
                    "request.session": request.session, # {"request.session": {	"context": {"lang": "en_US","tz": "Asia/Dubai","uid": 1	},"db": "","debug": "","geoip": {},"login": "","session_token": "","uid": 0} }
                }, indent=4, sort_keys=True, default=str),
        )


    @validate_token
    @http.route("/api/clinic_appointment/create", methods=["POST"], type="http", auth="none", csrf=False)
    def create_appointment(self, **post):
        user_id = request.uid
        user_obj = request.env['res.users'].browse(user_id)
        payload = request.httprequest.data.decode()
        payload = json.loads(payload)
        print(payload.get("appoint_start_date"))
        appoint_start_date = datetime.datetime.strptime(payload.get("appoint_start_date"), "%d/%m/%Y %H:%M")
        appoint_stop_date = datetime.datetime.strptime(payload.get("appoint_stop_date"), "%d/%m/%Y %H:%M")
        appoint_obj = request.env['patient.appointment']
        new_appoint = appoint_obj.with_user(user_obj).create({ # with_user checks if the user has the creating privilege/permission
            'start': appoint_start_date,
            'stop': appoint_stop_date,
        })
        if new_appoint:
            return valid_response([{"appointment_id": new_appoint.id, "result": "New Appointment Created Successfully"}], status=201)
        else:
            return invalid_response(
                "Error", "Failed to Create New Appointment", 401,
            )

    # @http.route(["/api/auth/token"], methods=["DELETE"], type="http", auth="none", csrf=False)
    # def delete(self, **post):
    #     """Delete a given token"""
    #     token = request.env["api.access_token"]
    #     access_token = post.get("access_token")
    #
    #     access_token = token.search([("token", "=", access_token)], limit=1)
    #     if not access_token:
    #         error = "Access token is missing in the request header or invalid token was provided"
    #         return invalid_response(400, error)
    #     for token in access_token:
    #         token.unlink()
    #     # Successful response:
    #     return valid_response([{"message": "access token %s successfully deleted" % (access_token,), "delete": True}])
