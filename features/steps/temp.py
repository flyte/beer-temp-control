from behave import given, then, when


@given("{thing:w} temp is {temp:g}")
def step(context, thing, temp):
    context.temps[thing.lower()] = temp


@when("{thing:w} temp changes to {temp:g}")
def step(context, thing, temp):
    context.temps[thing.lower()] = temp


@then("direction is {direction}")
def step(context, direction):
    # TODO: Tasks pending completion -@flyte at 29/06/2020, 17:04:09
    # Make this use the actual temp control engine
    return True
