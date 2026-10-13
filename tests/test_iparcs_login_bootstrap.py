import http.cookiejar
import unittest
from tennisrungs_mcp.iparcs_consumer import BoundaryError
from tennisrungs_mcp.iparcs_login_bootstrap import (AnonymousLoginSession, ExactSignInRedirect, FINAL_SIGNIN, SIGNIN,
                                  build_bootstrapped_login_request, classify_login_response,
                                  cookie_scope, parse_bootstrap)


def html(enabled=True,failed=1,tenant="/atlantadprca"):
    return '<script>window.__siteBaseName = "'+tenant+'";window.__csrfToken = "synthetic-csrf-marker-0001";window.__version="26.13.45";window.__reduxInitialState={configurations:{"enable_recaptcha_for_account":'+str(enabled).lower()+',"enable_recaptcha_failed_count":'+str(failed)+'}};</script>'


def jar(extra=None):
    j=http.cookiejar.CookieJar()
    for n,d in [("JSESSIONID","anc.apm.activecommunities.com"),("atlantadprca_JSESSIONID",".apm.activecommunities.com"),("atlantadprca_LOGGED_JSESSIONID",".apm.activecommunities.com")]+(extra or []):
        j.set_cookie(http.cookiejar.Cookie(0,n,"synthetic-cookie-marker",None,False,d,d.startswith('.'),d.startswith('.'),"/",True,True,None,True,None,None,{"HttpOnly":None}))
    return j


def response(**kw):
    r=dict(success=True,message="",error_type=0,need_verify_recaptcha=False,security_sign_token=None,
           public_customer_id=None,redirect_url=None,campaign_id=-1,ak_update_succeed=False)
    r.update(kw);return dict(headers={"response_code":"0000"},body={"result":r})


class Tests(unittest.TestCase):
    def test_static_bootstrap_no_javascript_eval(self):
        ctx=parse_bootstrap(html(),FINAL_SIGNIN)
        self.assertFalse(ctx.first_attempt_requires_recaptcha)
        self.assertFalse(ctx.authenticated)
        self.assertNotIn("synthetic-csrf-marker",repr(ctx))

    def test_wrong_tenant_or_url_rejected(self):
        for document,url in [(html(tenant="/other"),FINAL_SIGNIN),(html(),SIGNIN),
                             (html(),"https://example.invalid/signin?locale=en-US")]:
            with self.assertRaises(BoundaryError):parse_bootstrap(document,url)

    def test_missing_duplicate_or_dynamic_token_rejected(self):
        for document in [html().replace('window.__csrfToken = "synthetic-csrf-marker-0001";',''),
                         html()+'<script>window.__csrfToken="synthetic-token-marker-0002";</script>',
                         html().replace('"synthetic-csrf-marker-0001"','readFromSomewhere()')]:
            with self.assertRaises(BoundaryError):parse_bootstrap(document,FINAL_SIGNIN)

    def test_security_configuration_required(self):
        with self.assertRaises(BoundaryError):parse_bootstrap(html().replace('"enable_recaptcha_failed_count":1','"unrelated":1'),FINAL_SIGNIN)

    def test_recapcha_formula_first_attempt_and_marker(self):
        self.assertTrue(parse_bootstrap(html(failed=0),FINAL_SIGNIN).first_attempt_requires_recaptcha)
        self.assertTrue(parse_bootstrap(html(),FINAL_SIGNIN,challenge_marker=True).first_attempt_requires_recaptcha)
        self.assertFalse(parse_bootstrap(html(enabled=False,failed=0),FINAL_SIGNIN).first_attempt_requires_recaptcha)

    def test_cookie_names_are_not_authentication(self):
        session=AnonymousLoginSession(parse_bootstrap(html(),FINAL_SIGNIN),jar(),object())
        diag=session.diagnostics()
        self.assertFalse(diag["authenticated_session_verified"])
        self.assertNotIn("synthetic-cookie-marker",repr(diag))
        self.assertNotIn("synthetic-cookie-marker",repr(session))

    def test_scope_rejects_other_tenant_or_domain(self):
        for extra in [[("other_JSESSIONID",".apm.activecommunities.com")],[("JSESSIONID",".activecommunities.com")],[("unexpected","anc.apm.activecommunities.com")]]:
            with self.assertRaises(BoundaryError):cookie_scope(jar(extra))

    def test_source_accurate_login_body_and_secret_free_repr(self):
        s=AnonymousLoginSession(parse_bootstrap(html(),FINAL_SIGNIN),jar(),object())
        req=build_bootstrapped_login_request(s,"synthetic-user","synthetic-password-marker",approval_reference="synthetic-only")
        self.assertEqual(set(req.body),{"login_name","password","signin_source_app","locale","ak_properties"})
        self.assertIsNone(req.body["ak_properties"])
        self.assertIn("locale=en-US",req.url)
        self.assertNotIn("force_logged_off",req.body)
        self.assertNotIn("synthetic-password-marker",repr(req))
        self.assertNotIn("synthetic-csrf-marker",repr(req))

    def test_credentials_not_constructed_without_approval_or_when_captcha_normal(self):
        s=AnonymousLoginSession(parse_bootstrap(html(),FINAL_SIGNIN),jar(),object())
        with self.assertRaises(BoundaryError):build_bootstrapped_login_request(s,"x","y",approval_reference="")
        s.context=parse_bootstrap(html(failed=0),FINAL_SIGNIN)
        with self.assertRaises(BoundaryError):build_bootstrapped_login_request(s,"x","y",approval_reference="synthetic")

    def test_numeric_duplicate_login_stops_without_retry_storage(self):
        for status,kind in [(200,12),(202,"12")]:
            result=classify_login_response(status,response(success=False,error_type=kind))
            self.assertEqual(result["outcome"],"STOP_DUPLICATE_LOGIN_PRESERVE_EXISTING_SESSION")
            self.assertFalse(result["retry_allowed"]);self.assertFalse(result["storage_allowed"])

    def test_normal_inert_fields_are_not_unknown_schema(self):
        result=classify_login_response(200,response())
        self.assertTrue(result["outcome"].startswith("LOGIN_CLAIMS_SUCCESS"))
        self.assertFalse(result["authenticated_session_verified"])

    def test_signing_redirect_donation_and_captcha_stops(self):
        for kw in [dict(security_sign_token="synthetic-signing-marker",public_customer_id="synthetic-id"),
                   dict(redirect_url="https://example.invalid"),dict(campaign_id=1),dict(need_verify_recaptcha=True),
                   dict(access_token="synthetic-token")]:
            result=classify_login_response(200,response(**kw))
            self.assertTrue(result["outcome"].startswith("STOP"))
            self.assertNotIn("synthetic",repr(result))

    def test_malformed_headers_or_error_types_stop(self):
        for raw in [None,{},dict(headers=[],body={}),response(error_type=True)]:
            self.assertTrue(classify_login_response(200,raw)["outcome"].startswith("STOP"))


if __name__=="__main__":unittest.main()
