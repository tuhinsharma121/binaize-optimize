from datetime import datetime, timedelta
from typing import List

import jwt
from fastapi import Depends, HTTPException, status
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext

from config import *
from optimization_platform.deployment.server_models import *
from optimization_platform.src.agents.client_agent import ClientAgent
from optimization_platform.src.agents.cookie_agent import CookieAgent
from optimization_platform.src.agents.dashboard_agent import DashboardAgent
from optimization_platform.src.agents.event_agent import EventAgent
from optimization_platform.src.agents.experiment_agent import ExperimentAgent
from optimization_platform.src.agents.variation_agent import VariationAgent
from optimization_platform.src.agents.visit_agent import VisitAgent
from utils.data_store.rds_data_store import RDSDataStore
from utils.date_utils import DateUtils
from utils.logger.pylogger import get_logger

logger = get_logger("server", "INFO")

tags_metadata = [
    {
        "name": "Client",
        "description": "Operations with clients. The **login** logic is also here."
    },
    {
        "name": "Experiment",
        "description": "Operations with experiments."
    },
    {
        "name": "Variation",
        "description": "Operations with variations.",
    },
    {
        "name": "Event",
        "description": "Operations with events.",
    },
    {
        "name": "Visit",
        "description": "Operations with visits.",
    },
    {
        "name": "Cookie",
        "description": "Operations with cookies.",
    },
    {
        "name": "Report",
        "description": "Operations with reports.",
    },

]

app = FastAPI(title="Binaize",
              description="Apis for Binaize Optim", docs_url="/bdocs", redoc_url=None,
              version="1.0.0", openapi_tags=tags_metadata, openapi_url="/api/v1/schemas/openapi.json")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.rds_data_store = RDSDataStore(host=AWS_RDS_HOST, port=AWS_RDS_PORT,
                                  dbname=AWS_RDS_DBNAME,
                                  user=AWS_RDS_USER,
                                  password=AWS_RDS_PASSWORD)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/schemas/client/token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_client(data_store, client_id: str):
    client_details = ClientAgent.get_client_details_for_client_id(data_store=data_store, client_id=client_id)
    if client_details is not None:
        return ShopifyClient(**client_details)


def authenticate_client(data_store, client_id: str, password: str):
    user = get_client(data_store, client_id)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(*, data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def _get_current_client(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        client_id = payload.get("sub")
        user = get_client(app.rds_data_store, client_id=client_id)
        if user is None:
            raise credentials_exception
        return user
    except Exception:
        raise credentials_exception


async def get_current_active_client(current_client: BaseClient = Depends(_get_current_client)):
    if current_client.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_client


@app.get("/", response_model=dict)
async def home_page():
    import time
    t = time.time()
    response = dict()
    response["message"] = app.description
    response["status"] = status.HTTP_200_OK
    logger.info("prod info message")
    logger.info(time.time() - t)
    return response


@app.post("/api/v1/schemas/client/sign_up", response_model=ResponseMessage, tags=["Client"],
          summary="Sign up a new client")
async def sign_up_new_client(new_client: NewClient):
    """
        Sign up a new client:
        - **client_id**: the e-mail id of the new client
        - **full_name**: full name of the new client
        - **company_name**: company name of the new client
        - **disabled**: *true* if the new client should be disabled else *false*
        - **password**: password used for signing up by the new client
    """

    user = get_client(app.rds_data_store, client_id=new_client.client_id)
    response = ResponseMessage()
    response.message = "Client_id {client_id} is already registered.".format(
        client_id=new_client.client_id)
    response.status = status.HTTP_409_CONFLICT
    if user is None:
        hashed_password = get_password_hash(new_client.password)
        ClientAgent.add_new_client(data_store=app.rds_data_store, client_id=new_client.client_id,
                                   full_name=new_client.full_name,
                                   company_name=new_client.company_name, hashed_password=hashed_password,
                                   disabled=new_client.disabled)
        response.message = "Sign up for new client with client_id {client_id} is successful.".format(
            client_id=new_client.client_id)
        response.status = status.HTTP_200_OK

    return response


@app.post("/api/v1/schemas/client/token", response_model=Token, tags=["Client"], summary="Login and get access token")
async def login_and_get_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
        The client logs in and get an access token for the session:
        - **username**: the e-mail id of the client used as client_id while signing up
        - **password**: password used for signing up by the client
    """

    user = authenticate_client(app.rds_data_store, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.client_id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/v1/schemas/client/details", response_model=BaseClient, tags=["Client"],
         summary="Get details of a logged in client")
async def get_client_details(*, current_client: LoggedinClient = Depends(
    get_current_active_client)):
    """
        Get details of a logged in client:
        - **access_token**: access token issued by the server to the logged in client
    """
    client = BaseClient(client_id=current_client.client_id, full_name=current_client.full_name,
                        company_name=current_client.company_name, disabled=current_client.disabled)
    return client


@app.post("/api/v1/schemas/client/add-credential", response_model=ResponseMessage, tags=["Client"],
          summary="Add shopify credentials to logged in client")
async def add_shopify_credentials_to_logged_in_client(*, current_client: LoggedinClient = Depends(
    get_current_active_client), shopify_credentials: ShopifyCredential):
    """
        Get details of a logged in client:
        - **access_token**: access token issued by the server to the logged in client
        - **shopify_app_api_key**: api key of the shopify private app
        - **shopify_app_password**: password of the shopify private app
        - **shopify_app_eg_url**: example url of the shopify private app
        - **shopify_app_shared_secret**: shared_secret of the shopify private app
    """

    ClientAgent.add_shopify_credentials_to_existing_client(data_store=app.rds_data_store,
                                                           client_id=current_client.client_id,
                                                           shopify_app_api_key=shopify_credentials.shopify_app_api_key,
                                                           shopify_app_password=shopify_credentials.shopify_app_password,
                                                           shopify_app_eg_url=shopify_credentials.shopify_app_eg_url,
                                                           shopify_app_shared_secret=shopify_credentials.shopify_app_shared_secret)
    response = ResponseMessage()
    response.message = "Addition of Shopify Credentials for client_id {client_id} is successful.".format(
        client_id=current_client.client_id)
    response.status = status.HTTP_200_OK
    return response


@app.post("/api/v1/schemas/experiment/create", response_model=Experiment, tags=["Experiment"],
          summary="Create a new experiment")
async def add_experiment(*, current_client: ShopifyClient = Depends(get_current_active_client),
                         new_experiment: BaseExperiment):
    """
        Create a new experiment for a logged in client:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_name**: name of the experiment
        - **page_type**: which page the experiment is for - *home*/*product*
        - **experiment_type**: type of the experiment - *multi-variate*/*ab-test*/*personalization*
        - **status**: status of the experiment - *active*/*archived*/*done*
    """
    creation_time = DateUtils.get_timestamp_now()
    last_updation_time = DateUtils.get_timestamp_now()
    experiment = ExperimentAgent.create_experiment_for_client_id(data_store=app.rds_data_store,
                                                                 client_id=current_client.client_id,
                                                                 experiment_name=new_experiment.experiment_name,
                                                                 page_type=new_experiment.page_type,
                                                                 experiment_type=new_experiment.experiment_type,
                                                                 status=new_experiment.status,
                                                                 creation_time=creation_time,
                                                                 last_updation_time=last_updation_time)
    return experiment


@app.get("/api/v1/schemas/experiment/list", response_model=List[Experiment], tags=["Experiment"],
         summary="List down all the experiments")
async def list_experiments(*, current_client: ShopifyClient = Depends(get_current_active_client)):
    """
        List down all the experiments for a logged in client:
        - **access_token**: access token issued by the server to the logged in client
    """
    experiment_ids = ExperimentAgent.get_experiments_for_client_id(data_store=app.rds_data_store,
                                                                   client_id=current_client.client_id)
    return experiment_ids


@app.post("/api/v1/schemas/variation/create", response_model=Variation, tags=["Variation"],
          summary="Create a new variation")
async def add_variation(*, current_client: ShopifyClient = Depends(get_current_active_client),
                        new_variation: NewVariation):
    """
        Create a new variation for an existing experiment of a logged in client:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
        - **variation_name**: name of the variation
        - **traffic_percentage**: percentage of traffic to be redirected to this variation
    """
    variation = VariationAgent.create_variation_for_client_id_and_experiment_id(data_store=app.rds_data_store,
                                                                                client_id=current_client.client_id,
                                                                                experiment_id=new_variation.experiment_id,
                                                                                variation_name=new_variation.variation_name,
                                                                                traffic_percentage=new_variation.traffic_percentage)
    return variation


@app.get("/api/v1/schemas/variation/redirection", response_model=Variation, tags=["Variation"],
         summary="Get the variation id to be redirected to")
async def get_variation_id_to_redirect(*, client_id: str, experiment_id: str, session_id: str):
    """
        Get the variation id to be redirected to when a visitor visits the client's website:
        - **client_id**: the e-mail id of the new client
        - **experiment_id**: id of the experiment
        - **session_id**: shopify_y attribute of shopify cookie
    """
    variation = VariationAgent.get_variation_id_to_recommend(data_store=app.rds_data_store,
                                                             client_id=client_id,
                                                             experiment_id=experiment_id,
                                                             session_id=session_id)
    creation_time = DateUtils.get_timestamp_now()
    EventAgent.register_event_for_client(data_store=app.rds_data_store, client_id=client_id,
                                         experiment_id=experiment_id,
                                         session_id=session_id,
                                         variation_id=variation["variation_id"], event_name="served",
                                         creation_time=creation_time)

    return variation


@app.post("/api/v1/schemas/event/register", response_model=ResponseMessage, tags=["Event"], summary="Register event")
async def register_event(*, event: Event):
    """
        Register conversion event when a visitor visits the client's website:
        - **client_id**: the e-mail id of the new client
        - **experiment_id**: id of the experiment
        - **session_id**: shopify_y attribute of shopify cookie
        - **variation_id**: id of the variation
        - **event_name**: name of the conversion event
    """

    creation_time = DateUtils.get_timestamp_now()
    EventAgent.register_event_for_client(data_store=app.rds_data_store, client_id=event.client_id,
                                         experiment_id=event.experiment_id,
                                         session_id=event.session_id, variation_id=event.variation_id,
                                         event_name=event.event_name, creation_time=creation_time)

    response = ResponseMessage()
    response.message = "Event registration for client_id {client_id} is successful.".format(
        client_id=event.client_id)
    response.status = status.HTTP_200_OK
    return response


@app.post("/api/v1/schemas/visit/register", response_model=ResponseMessage, tags=["Visit"], summary="Register visit")
async def register_visit(*, visit: Visit):
    """
        Register visit event when a visitor visits the client's website:
        - **client_id**: the e-mail id of the new client
        - **session_id**: shopify_y attribute of shopify cookie
        - **event_name**: name of the visit event
        - **url**: url visited by the website visitor
    """
    creation_time = DateUtils.get_timestamp_now()
    VisitAgent.register_visit_for_client(data_store=app.rds_data_store, client_id=visit.client_id,
                                         session_id=visit.session_id,
                                         event_name=visit.event_name, creation_time=creation_time, url=visit.url)

    response = ResponseMessage()
    response.message = "Visit registration for client_id {client_id} and event name {event_name} is successful.".format(
        client_id=visit.client_id, event_name=visit.event_name)
    response.status = status.HTTP_200_OK
    return response


@app.post("/api/v1/schemas/cookie/register", response_model=ResponseMessage, tags=["Cookie"],
          summary="Register cookie information")
async def register_cookie(*, cookie: Cookie):
    """
        Register cookie information when a visitor visits the client's website::
        - **client_id**: the e-mail id of the new client
        - **session_id**: shopify_y attribute of shopify cookie
        - **shopify_s**: shopify_s attribute of shopify cookie
        - **cart_token**: cart_token attribute of shopify cookie
    """
    creation_time = DateUtils.get_timestamp_now()
    CookieAgent.register_cookie_for_client(data_store=app.rds_data_store, client_id=cookie.client_id,
                                           session_id=cookie.session_id,
                                           shopify_s=cookie.shopify_s, cart_token=cookie.cart_token,
                                           creation_time=creation_time)

    response = ResponseMessage()
    response.message = "Cookie registration for client_id {client_id} is successful.".format(
        client_id=cookie.client_id)
    response.status = status.HTTP_200_OK
    return response


@app.get("/api/v1/schemas/report/session-count", response_model=dict, tags=["Report"], summary="Get session count")
async def get_session_count_for_dashboard(*, current_client: ShopifyClient = Depends(get_current_active_client),
                                          experiment_id: str):
    """
        Get session count of all the variations of an existing experiment of a logged in client for last 7 days
        at a daily level:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
    """
    result = DashboardAgent.get_session_count_per_variation_over_time(data_store=app.rds_data_store,
                                                                      client_id=current_client.client_id,
                                                                      experiment_id=experiment_id)

    return result


@app.get("/api/v1/schemas/report/visitor-count", response_model=dict, tags=["Report"], summary="Get visitor count")
async def get_visitor_count_for_dashboard(*, current_client: ShopifyClient = Depends(get_current_active_client),
                                          experiment_id: str):
    """
        Get visitor count of all the variations of an existing experiment of a logged in client for last 7 days
        at a daily level:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
    """
    result = DashboardAgent.get_visitor_count_per_variation_over_time(data_store=app.rds_data_store,
                                                                      client_id=current_client.client_id,
                                                                      experiment_id=experiment_id)

    return result


@app.get("/api/v1/schemas/report/conversion-rate", response_model=dict, tags=["Report"], summary="Get conversion rate")
async def get_conversion_rate_for_dashboard(*, current_client: ShopifyClient = Depends(get_current_active_client),
                                            experiment_id: str):
    """
        Get conversion rate of all the variations of an existing experiment of a logged in client for last 7 days
        at a daily level:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
    """
    result = DashboardAgent.get_conversion_rate_per_variation_over_time(data_store=app.rds_data_store,
                                                                        client_id=current_client.client_id,
                                                                        experiment_id=experiment_id)

    return result


@app.get("/api/v1/schemas/report/conversion-table", response_model=List[dict], tags=["Report"],
         summary="Get conversion table")
async def get_conversion_table_for_dashboard(*, current_client: ShopifyClient = Depends(get_current_active_client),
                                             experiment_id: str):
    """
        Get conversion table of all the variations of an existing experiment of a logged in client till now:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
    """
    result = DashboardAgent.get_conversion_rate_of_experiment(data_store=app.rds_data_store,
                                                              client_id=current_client.client_id,
                                                              experiment_id=experiment_id)

    return result


@app.get("/api/v1/schemas/report/experiment-summary", response_model=dict, tags=["Report"],
         summary="Get experiment summary")
async def get_experiment_summary(*, current_client: ShopifyClient = Depends(get_current_active_client),
                                 experiment_id: str):
    """
        Get experiment summary of an existing experiment of a logged in client:
        - **access_token**: access token issued by the server to the logged in client
        - **experiment_id**: id of the experiment
    """

    result = DashboardAgent.get_summary_of_experiment(data_store=app.rds_data_store,
                                                      client_id=current_client.client_id,
                                                      experiment_id=experiment_id)

    return result


@app.get("/api/v1/schemas/report/shop-funnel", response_model=dict, tags=["Report"],
         summary="Get shop funnel analytics")
async def get_shop_funnel_analytics_for_dashboard(*,
                                                  current_client: ShopifyClient = Depends(get_current_active_client)):
    """
        Get shop funnel analytics of the client's website till now:
        - **access_token**: access token issued by the server to the logged in client
    """
    result = DashboardAgent.get_shop_funnel_analytics(data_store=app.rds_data_store,
                                                      client_id=current_client.client_id)

    return result


@app.get("/api/v1/schemas/report/product-conversion", response_model=dict, tags=["Report"],
         summary="Get product conversion analytics")
async def get_product_conversion_analytics_for_dashboard(*, current_client: ShopifyClient = Depends(
    get_current_active_client)):
    """
        Get product conversion analytics of the client's website till now:
        - **access_token**: access token issued by the server to the logged in client
    """
    result = DashboardAgent.get_product_conversion_analytics(data_store=app.rds_data_store,
                                                             client_id=current_client.client_id)

    return result


@app.get("/api/v1/schemas/report/landing-page", response_model=dict, tags=["Report"],
         summary="Get landing page analytics")
async def get_landing_page_analytics_for_dashboard(*, current_client: ShopifyClient = Depends(get_current_active_client)
                                                   ):
    """
        Get landing page analytics of the client's website till now:
        - **access_token**: access token issued by the server to the logged in client
    """
    result = DashboardAgent.get_landing_page_analytics(data_store=app.rds_data_store,
                                                       client_id=current_client.client_id)

    return result
