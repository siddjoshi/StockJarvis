# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

import cherrypy
from flask import Flask, jsonify


def JarvisWebOn():
    # sample app with flask
    app = Flask(__name__)

    ## Handle home page
    @app.route('/')
    def hello_world():
        return "Hello World"

    ## This is Kiteconnect Redirect URL
    ## Request token will be received on this URL
    @app.route('/postlogin', methods=['POST'])
    def get_rtoken():
        ## Get the token from the request
        rtoken = cherrypy.request.params.get('request_token')
        ## Save the token to the file

    ## Just for fun
    @app.route('/sid')
    def sid_world():
        return "Hello Sid"

    ## Kiteconnect will postback to this URL
    @app.route('/jarvispostback', methods=['POST'])  # GET requests will be blocked
    def json_example():
        resp = jsonify(success=True)
        resp.status_code = 200
        return resp

    cherrypy.tree.graft(app, "/")

    # Unsubscribe the default server
    cherrypy.server.unsubscribe()

    # Instantiate a new server object
    server = cherrypy._cpserver.Server()

    # Configure the server object
    server.socket_host = "0.0.0.0"
    server.socket_port = 5000
    server.thread_pool = 30

    # Subscribe this server
    server.subscribe()

    cherrypy.engine.start()
    cherrypy.engine.block()
