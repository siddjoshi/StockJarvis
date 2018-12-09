import queue

q = queue.Queue()

for i in range(5):
    q.put(i)

while not q.empty():
    print(q.get())


class Job(object):
    def __init__(self, priority, description):
        self.priority = priority
        self.description = description
        print('New job:', description)
        return

    def __cmp__(self, other):
        return cmp(self.priority, other.priority)


q = queue.PriorityQueue()

q.put(Job(3, 'Mid-level job'))
q.put(Job(10, 'Low-level job'))
q.put(Job(1, 'Important job'))

while not q.empty():
    next_job = q.get()
    print('Processing job:', next_job.description)
