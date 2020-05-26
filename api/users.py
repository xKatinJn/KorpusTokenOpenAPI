import json
import hashlib
import datetime

from app.api import bp
from app.scripts.service import get_questionnaires_access
from app.api.errors import bad_request
from app.models import db, User, Teams, Membership, UserStatuses, QuestionnaireTable, Questionnaire
from app.scripts.service import login_validating, email_validating
from flask import request, jsonify


@bp.route('/users/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'GET':
        payload = {
            'teams': [team.name for team in Teams.query.all()]
        }
        response = jsonify(payload)
        response.status_code = 200
        return response
    elif request.method == 'POST':
        data = request.get_json() or {}
        if type(data) == str:
            data = json.loads(data)
        payload = {
            'message': '',
            'validation_errors': []
        }
        if len(data) >= 10:
            if not login_validating(data['login']):
                payload['message'] += 'Login validating failed. Login is already using. '
                payload['validation_errors'].append('login')
            if not email_validating(data['email']):
                payload['message'] += 'Email validating failed. Email is already using.'
                payload['validation_errors'].append('email')
            if len(payload['validation_errors']) > 0:
                response = jsonify(payload)
                response.status_code = 400
                return response

            data['birthday'] = datetime.datetime.strptime(data['birthday'], '%d-%m-%Y')
            token_word = # СУПЕР СЕКРЕТНЫЙ И СЛОЖНЫЙ АЛГОРИТМ                                  
            token_word = hashlib.sha256(token_word.encode()).hexdigest()
            user = User(
                data['email'],
                data['login'],
                data['tg_nickname'],
                data['courses'],
                data['birthday'],
                data['education'],
                data['work_exp'],
                data['sex'],
                data['name'],
                data['surname'],
                token_word
            )
            user.set_password(data['password'])
            db.session.add(user)
            db.session.commit()

            user = User.query.filter_by(email=data['email']).first()
            if 'team' in data:
                for team in data['team']:
                    user_team = Membership(user_id=user.id,
                                           team_id=Teams.query.filter_by(name=team).first().id,
                                           role_id=0)
                    db.session.add(user_team)
            user_status = UserStatuses(user_id=user.id, status_id=3)
            db.session.add(user_status)
            db.session.commit()

            payload['message'] = 'Registered'
            payload['token'] = token_word
            response = jsonify(payload)
            response.status_code = 200
            return response
        else:
            return bad_request('Got not enough DATA')


@bp.route('/users/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    if type(data) == str:
        data = json.loads(data)
    if ('login' not in data) or ('password' not in data):
        return bad_request('Must include login and password fields')

    user_login = data['login']
    user_password = data['password']
    user_client = User.query.filter_by(login=user_login).first()
    payload = {}
    if user_client:
        if user_client.check_password(user_password):
            payload['message'] = 'Logged'
            if not user_client.token:
                token_word = '{}{}{}{}'.format(user_client.login, user_client.email, user_client.surname,
                                               datetime.datetime.now().timestamp())
                user_client.token = hashlib.sha256(token_word.encode()).hexdigest()
                db.session.commit()
            payload['token'] = user_client.token
        else:
            payload['message'] = 'Login or password incorrect'
    else:
        payload['message'] = 'Login or password incorrect'

    response = jsonify(payload)
    response.status_code = 200
    return response


@bp.route('/users/get_user', methods=['POST'])
def get_user():
    data = request.get_json() or {}
    if type(data) == str:
        data = json.loads(data)
    if 'token' not in data:
        return bad_request('Must include user token')

    payload = {
        'message': 'OK'
    }
    request_user = User.query.filter_by(token=data['token']).first()
    if not request_user:
        return bad_request('Token invalid')
    if 'params' not in data:
        return bad_request('Must include params')

    if data['params'][0] == 'ALL':
        payload.update(request_user.to_dict())
        payload.update(get_questionnaires_access(request_user))
        teams = Membership.query.filter_by(user_id=request_user.id).first()
        payload['teams'] = teams.team_id if teams else 0
    else:
        for param in data['params']:
            if param == 'QUESTIONNAIRE_SELF':
                payload['questionnaire_self'] = get_questionnaires_access(request_user)['questionnaire_self']
                continue

            if param == 'QUESTIONNAIRE_TEAM':
                payload['questionnaire_team'] = get_questionnaires_access(request_user)['questionnaire_team']
                continue

            if param == 'MEMBERSHIP':
                payload['membership'] = True if Membership.query.filter_by(user_id=request_user.id).first() else False
                continue

            if param == 'TEAMS':
                teams = Membership.query.filter_by(user_id=request_user.id).first()
                payload['teams'] = teams.team_id if teams else 0
                # [team.team_id for team in Membership.query.filter_by(user_id=request_user.id).all()]
                continue

            try:
                payload[param.lower()] = getattr(request_user, param.lower())
            except AttributeError:
                return bad_request(f'AttributeError: {param}')
    response = jsonify(payload)
    response.status_code = 200
    return response


@bp.route('/users/get_teammates', methods=['POST'])
def get_teammates():
    data = request.get_json() or {}
    if type(data) == str:
        data = json.loads(data)
    if 'token' not in data:
        return bad_request('Must include user token')
    payload = {
        'message': 'OK'
    }
    request_user = User.query.filter_by(token=data['token']).first()
    if Membership.query.filter_by(user_id=request_user.id).first():
        if data['team_id']:
            try:
                data['team_id'] = int(data['team_id'])
            except Exception:
                return bad_request('team_id must be integer')

            if Membership.query.filter_by(user_id=request_user.id, team_id=data['team_id']).first():
                teammates = [User.query.filter_by(id=teammate.user_id).first()
                             for teammate in Membership.query.filter_by(team_id=data['team_id']).all()
                             if teammate.user_id != request_user.id]
                teammates_dict = {}
                for teammate in teammates:
                    if teammate:
                        teammates_dict.update({teammate.name + ' ' + teammate.surname: teammate.id})
                payload['teammates'] = teammates_dict
            else:
                return bad_request('User is not in that team')
        else:
            return bad_request('Must include team_id')
    else:
        return bad_request('User has not got team')
    response = jsonify(payload)
    response.status_code = 200
    return response
