from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from robots.models import Robo


@login_required
def robot_list(request):
    robos = Robo.objects.all()
    return render(request, "robots/list.html", {"robos": robos})