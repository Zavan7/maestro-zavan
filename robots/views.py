from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def robot_list(request):
    return render(request, "robots/list.html")