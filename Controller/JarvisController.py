from multiprocessing import Process

from Web import JarvisWeb


def f(name):
    print("hello", name)


## Function to start the Cherrypi web server
def startJarvisWebWorker():
    JarvisWeb.JarvisWebOn()


def startJarvisAnalysisEngine():
    print("Starting Jarvis Analysis Engine")


## Main Function
if __name__ == '__main__':
    p = Process(target=startJarvisWebWorker)

    ## Start the web worker
    p.start()

    ## wait till web worker is closed
    p.join()
