import threading
import werkzeug.serving


from __init__ import app
import submit_loop 


if not werkzeug.serving.is_running_from_reloader():
    submit_thread = threading.Thread(target=submit_loop.run_loop)
    submit_thread.start()
    
