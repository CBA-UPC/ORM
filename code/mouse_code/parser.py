# %%
import esprima
import jsbeautifier
import quickle

decoder = quickle.Decoder()

# %%
def extractScriptFromHTML(html):
    splitted = html.replace('</script>','<script').split('<script')
    scriptcuts = []
    for i in range(1, len(splitted), 2):
        start = 0
        stringQuote = None
        skipNext = False
        while stringQuote != None or splitted[i][start] != '>':
            if skipNext:
                skipNext = False
            elif splitted[i][start] == '\\':
                start += 1
                skipNext = True
            if not skipNext and (splitted[i][start] == '\'' or splitted[i][start] == '"'):
                if stringQuote == None:
                    stringQuote = splitted[i][start]
                elif stringQuote == splitted[i][start]:
                    stringQuote = None
            start += 1
        scriptcuts.append(splitted[i][start+1:])
    return '\n'.join(scriptcuts)

# %%
def operateStatement(statement, previous, nodes):
    if statement == None:
        return { '_id': -1 }
    copyStatement = {}
    copyStatement['_id'] = len(nodes)
    copyStatement['type'] = statement.type
    copyStatement['previous'] = previous
    copyStatement['range'] = [statement.range[0], statement.range[1]]
    copyStatement['loc'] = { 
        'start': { 'line': statement.loc.start.line, 'column': statement.loc.start.column }, 
        'end': { 'line': statement.loc.end.line, 'column': statement.loc.end.column } 
    }
    nodes.append(copyStatement)
    if statement.type == 'BlockStatement':
        copyStatement['body'] = []
        for insideStatement in statement.body:
            insideStatementCopy = operateStatement(insideStatement, copyStatement['_id'], nodes)
            copyStatement['body'].append(insideStatementCopy['_id'])
    elif statement.type == 'BreakStatement':
        label = operateExpression(statement.label, copyStatement['_id'], nodes)
        copyStatement['label'] = label['_id']
    elif statement.type == 'ClassDeclaration':
        id = operateExpression(statement.id, copyStatement['_id'], nodes)
        copyStatement['id'] = id['_id']
        superClass = operateExpression(statement.superClass, copyStatement['_id'], nodes)
        copyStatement['superClass'] = superClass['_id']
        copyStatement['body'] = {}
        copyStatement['body']['body'] = []
        for method in statement.body.body:
            copyStatement['body']['body'].append({})
            key = operateExpression(method.key, copyStatement['_id'], nodes)
            copyStatement['body']['body'][-1]['key'] = key['_id']
            value = operateExpression(method.value, copyStatement['_id'], nodes)
            copyStatement['body']['body'][-1]['value'] = value['_id']
    elif statement.type == 'ContinueStatement':
        label = operateExpression(statement.label, copyStatement['_id'], nodes)
        copyStatement['label'] = label['_id']
    elif statement.type == 'DoWhileStatement':
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
        test = operateExpression(statement.test, copyStatement['_id'], nodes)
        copyStatement['test'] = test['_id']
    elif statement.type == 'ExpressionStatement':
        expression = operateExpression(statement.expression, copyStatement['_id'], nodes)
        copyStatement['expression'] = expression['_id']
        copyStatement['directive'] = statement.directive
    elif statement.type == 'ForStatement':
        init = operateExpression(statement.init, copyStatement['_id'], nodes)
        copyStatement['init'] = init['_id']
        test = operateExpression(statement.test, copyStatement['_id'], nodes)
        copyStatement['test'] = test['_id']
        update = operateExpression(statement.update, copyStatement['_id'], nodes)
        copyStatement['update'] = update['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type == 'ForInStatement':
        left = operateExpression(statement.left, copyStatement['_id'], nodes)
        copyStatement['left'] = left['_id']
        right = operateExpression(statement.right, copyStatement['_id'], nodes)
        copyStatement['right'] = right['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type == 'ForOfStatement':
        left = operateExpression(statement.left, copyStatement['_id'], nodes)
        copyStatement['left'] = left['_id']
        right = operateExpression(statement.right, copyStatement['_id'], nodes)
        copyStatement['right'] = right['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type == 'FunctionDeclaration':
        id = operateExpression(statement.id, copyStatement['_id'], nodes)
        copyStatement['id'] = id['_id']
        copyStatement['params'] = []
        for parameter in statement.params:
            copyParameter = operateExpression(parameter, copyStatement['_id'], nodes)
            copyStatement['params'].append(copyParameter['_id'])
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
        copyStatement['generator'] = statement.generator
        copyStatement['async'] = getattr(statement, 'async')
        copyStatement['expression'] = statement.expression
    elif statement.type == 'IfStatement':
        test = operateExpression(statement.test, copyStatement['_id'], nodes)
        copyStatement['test'] = test['_id']
        consequent = operateStatement(statement.consequent, copyStatement['_id'], nodes)
        copyStatement['consequent'] = consequent['_id']
        alternative = operateStatement(statement.alternate, copyStatement['_id'], nodes)
        copyStatement['alternative'] = alternative['_id']
    elif statement.type == 'LabeledStatement':
        label = operateExpression(statement.label, copyStatement['_id'], nodes)
        copyStatement['label'] = label['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type == 'ReturnStatement':
        argument = operateExpression(statement.argument, copyStatement['_id'], nodes)
        copyStatement['argument'] = argument['_id']
    elif statement.type == 'SwitchStatement':
        discriminant = operateExpression(statement.discriminant, copyStatement['_id'], nodes)
        copyStatement['discriminant'] = discriminant['_id']
        copyStatement['cases'] = []
        for case in statement.cases:
            test = operateExpression(case.test, copyStatement['_id'], nodes)
            copyStatement['cases'].append({})
            copyStatement['cases'][-1]['test'] = test['_id']
            copyStatement['cases'][-1]['consequent'] = []
            for consequent in case.consequent:
                copyConsequent = operateStatement(consequent, copyStatement['_id'], nodes)
                copyStatement['cases'][-1]['consequent'].append(copyConsequent['_id'])
    elif statement.type == 'ThrowStatement':
        argument = operateExpression(statement.argument, copyStatement['_id'], nodes)
        copyStatement['argument'] = argument['_id']
    elif statement.type == 'TryStatement':
        block = operateStatement(statement.block, copyStatement['_id'], nodes)
        copyStatement['block'] = block['_id']
        handler = operateExpression(statement.handler, copyStatement['_id'], nodes)
        copyStatement['handler'] = handler['_id']
        finalizer = operateStatement(statement.finalizer, copyStatement['_id'], nodes)
        copyStatement['finalizer'] = finalizer['_id']
    elif statement.type == 'VariableDeclaration':
        copyStatement['declarations'] = []
        for declaration in statement.declarations:
            copyDeclaration = operateExpression(declaration, copyStatement['_id'], nodes)
            copyStatement['declarations'].append(copyDeclaration['_id'])
        copyStatement['kind'] = statement.kind
    elif statement.type == 'WhileStatement':
        test = operateExpression(statement.test, copyStatement['_id'], nodes)
        copyStatement['test'] = test['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type == 'WithStatement':
        object = operateExpression(statement.object, copyStatement['_id'], nodes)
        copyStatement['object'] = object['_id']
        body = operateStatement(statement.body, copyStatement['_id'], nodes)
        copyStatement['body'] = body['_id']
    elif statement.type in ['EmptyStatement', 'DebuggerStatement']:
        pass
    return copyStatement

# %%
def operateExpression(expression, previous, nodes):
    if expression == None:
        return {  '_id': -1 }
    copyExpression = {}
    copyExpression['_id'] = len(nodes)
    copyExpression['type'] = expression.type
    copyExpression['previous'] = previous
    copyExpression['range'] = [expression.range[0], expression.range[1]]
    copyExpression['loc'] = { 
        'start': { 'line': expression.loc.start.line, 'column': expression.loc.start.column }, 
        'end': { 'line': expression.loc.end.line, 'column': expression.loc.end.column } 
    }
    nodes.append(copyExpression)
    if expression.type == 'Identifier':
        copyExpression['name'] = expression.name
    elif expression.type == 'Literal':
        # copyExpression['value'] = expression.value
        copyExpression['raw'] = expression.raw
        # copyExpression['regex'] = expression.regex
    elif expression.type == 'ArrayExpression':
        copyExpression['elements'] = []
        for element in expression.elements:
            copyElement = operateExpression(element, copyExpression['_id'], nodes)
            copyExpression['element'] = copyElement['_id']
    elif expression.type == 'SpreadElement':
        argument  = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
    elif expression.type == 'ObjectExpression':
        copyExpression['properties'] = []
        for property in expression.properties:
            copyProperty = operateExpression(property, copyExpression['_id'], nodes)
            copyExpression['properties'].append(copyProperty['_id'])
    elif expression.type == 'FunctionExpression':
        id  = operateExpression(expression.id, copyExpression['_id'], nodes)
        copyExpression['id'] = id['_id']
        copyExpression['params'] = []
        for param in expression.params:
            copyParam = operateExpression(param, copyExpression['_id'], nodes)
            copyExpression['params'].append(copyParam['_id'])
        body = operateStatement(expression.body, copyExpression['_id'], nodes)
        copyExpression['body'] = body['_id']
        copyExpression['generator'] = expression.generator
        copyExpression['async'] = getattr(expression, 'async')
        copyExpression['expression'] = expression.expression
    elif expression.type == 'ArrowFunctionExpression':
        id  = operateExpression(expression.id, copyExpression['_id'], nodes)
        copyExpression['id'] = id['_id']
        copyExpression['params'] = []
        for param in expression.params:
            param = operateExpression(param, copyExpression['_id'], nodes)
            copyExpression['params'].append(param['_id'])
        if expression.body.type == 'BlockStatement':
            body = operateStatement(expression.body, copyExpression['_id'], nodes)
            copyExpression['body'] = body['_id']
        else:
            body = operateExpression(expression.body, copyExpression['_id'], nodes)
            copyExpression['body'] = body['_id']
        copyExpression['generator'] = expression.generator
        copyExpression['async'] = getattr(expression, 'async')
        copyExpression['expression'] = expression.expression
    elif expression.type == 'ClassExpression':
        id = operateExpression(expression.id, copyExpression['_id'], nodes)
        copyExpression['id'] = id['_id']
        superClass = operateExpression(expression.superClass, copyExpression['_id'], nodes)
        copyExpression['superClass'] = superClass['_id']
        copyExpression['body'] = {}
        copyExpression['body']['body'] = []
        for method in expression.body.body:
            copyExpression['body']['body'].append({})
            key = operateExpression(method.key, copyExpression['_id'], nodes)
            copyExpression['body']['body'][-1]['key'] = key['_id']
            copyExpression['body']['body'][-1]['computed'] = method.computed
            value = operateExpression(method.value, copyExpression['_id'], nodes)
            copyExpression['body']['body'][-1]['value'] = value['_id']
            copyExpression['body']['body'][-1]['kind'] = method.kind
            copyExpression['body']['body'][-1]['static'] = method.static
    elif expression.type == 'TaggedTemplateExpression':
        tag = operateExpression(expression.tag, copyExpression['_id'], nodes)
        copyExpression['tag'] = tag['_id']
        quasi = operateExpression(expression.quasi, copyExpression['_id'], nodes)
        copyExpression['quasi'] = quasi['_id']
    elif expression.type == 'MemberExpression':
        copyExpression['computed'] = expression.computed
        object = operateExpression(expression.object, copyExpression['_id'], nodes)
        copyExpression['object'] = object['_id']
        property = operateExpression(expression.property, copyExpression['_id'], nodes)
        copyExpression['property'] = property['_id']
    elif expression.type == 'CallExpression':
        callee = operateExpression(expression.callee, copyExpression['_id'], nodes)
        copyExpression['callee'] = callee['_id']
        copyExpression['arguments'] = []
        for argument in expression.arguments:
            copyArgument = operateExpression(argument, copyExpression['_id'], nodes)
            copyExpression['arguments'].append(copyArgument['_id'])
    elif expression.type == 'NewExpression':
        callee = operateExpression(expression.callee, copyExpression['_id'], nodes)
        copyExpression['callee'] = callee['_id']
        copyExpression['arguments'] = []
        for argument in expression.arguments:
            copyArgument = operateExpression(argument, copyExpression['_id'], nodes)
            copyExpression['arguments'].append(copyArgument['_id'])
    elif expression.type == 'UpdateExpression':
        copyExpression['operator'] = expression.operator
        argument = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
        copyExpression['prefix'] = expression.prefix
    elif expression.type == 'AwaitExpression':
        argument = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
    elif expression.type == 'UnaryExpression':
        copyExpression['operator'] = expression.operator
        argument = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
    elif expression.type == 'BinaryExpression':
        copyExpression['operator'] = expression.operator
        left = operateExpression(expression.left, copyExpression['_id'], nodes)
        copyExpression['left'] = left['_id']
        right = operateExpression(expression.right, copyExpression['_id'], nodes)
        copyExpression['right'] = right['_id']
    elif expression.type == 'LogicalExpression':
        copyExpression['operator'] = expression.operator
        left = operateExpression(expression.left, copyExpression['_id'], nodes)
        copyExpression['left'] = left['_id']
        right = operateExpression(expression.right, copyExpression['_id'], nodes)
        copyExpression['right'] = right['_id']
    elif expression.type == 'ConditionalExpression':
        test = operateExpression(expression.test, copyExpression['_id'], nodes)
        copyExpression['test'] = test['_id']
        consequent = operateExpression(expression.consequent, copyExpression['_id'], nodes)
        copyExpression['consequent'] = consequent['_id']
        alternate = operateExpression(expression.alternate, copyExpression['_id'], nodes)
        copyExpression['alternate'] = alternate['_id']
    elif expression.type == 'YieldExpression':
        argument = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
        copyExpression['delegate'] = expression.delegate
    elif expression.type == 'AssignmentExpression':
        copyExpression['operator'] = expression.operator
        left = operateExpression(expression.left, copyExpression['_id'], nodes)
        copyExpression['left'] = left['_id']
        right = operateExpression(expression.right, copyExpression['_id'], nodes)
        copyExpression['right'] = right['_id']
    elif expression.type == 'SequenceExpression':
        copyExpression['expressions'] = []
        for insideExpression in expression.expressions:
            copyInsideExpression = operateExpression(insideExpression, copyExpression['_id'], nodes)
            copyExpression['expressions'].append(copyInsideExpression['_id'])
    elif expression.type == 'VariableDeclaration':
        copyExpression['declarations'] = []
        for declaration in expression.declarations:
            copyDeclaration = operateExpression(declaration, copyExpression['_id'], nodes)
            copyExpression['declarations'].append(copyDeclaration['_id'])
        copyExpression['kind'] = expression.kind
    elif expression.type == 'VariableDeclarator':
            id = operateExpression(expression.id, copyExpression['_id'], nodes)
            copyExpression['id'] = id['_id']
            init = operateExpression(expression.init, copyExpression['_id'], nodes)
            copyExpression['init'] = init['_id']
    elif expression.type == 'Property':
            key = operateExpression(expression.key, copyExpression['_id'], nodes)
            copyExpression['key'] = key['_id']
            copyExpression['computed'] = expression.computed
            value = operateExpression(expression.value, copyExpression['_id'], nodes)
            copyExpression['value'] = value['_id']
            copyExpression['kind'] = expression.kind
            copyExpression['method'] = expression.method
            copyExpression['shorthand'] = expression.shorthand
    elif expression.type == 'CatchClause':
        param = operateExpression(expression.param, copyExpression['_id'], nodes)
        copyExpression['param'] = param
        body = operateStatement(expression.body, copyExpression['_id'], nodes)
        copyExpression['body'] = body
    elif expression.type == 'TemplateLiteral':
        copyExpression['quasis'] = []
        for quasi in expression.quasis:
            copyQuasi = operateExpression(quasi, copyExpression['_id'], nodes)
            copyExpression['quasis'].append(copyQuasi['_id'])
        copyExpression['expressions'] = []
        for insideExpression in expression.expressions:
            copyInsideExpression = operateExpression(insideExpression, copyExpression['_id'], nodes)
            copyExpression['expressions'].append(copyInsideExpression['_id'])
    elif expression.type == 'TemplateElement':
        copyExpression['value'] = expression.value
        copyExpression['tail'] = expression.tail
    elif expression.type == 'ArrayPattern':
        copyExpression['elements'] = []
        for element in expression.elements:
            copyElement = operateExpression(element, copyExpression['_id'], nodes)
            copyExpression['elements'].append(copyElement['_id'])
    elif expression.type == 'RestElement':
        argument = operateExpression(expression.argument, copyExpression['_id'], nodes)
        copyExpression['argument'] = argument['_id']
    elif expression.type == 'AssignmentPattern':
        left = operateExpression(expression.left, copyExpression['_id'], nodes)
        copyExpression['left'] = left['_id']
        right = operateExpression(expression.right, copyExpression['_id'], nodes)
        copyExpression['right'] = right['_id']
    elif expression.type == 'ObjectPattern':
        copyExpression['properties'] = []
        for property in expression.properties:
            copyProperty = operateExpression(property, copyExpression['_id'], nodes)
            copyExpression['properties'].append(copyProperty['_id'])
    elif expression.type in ['ThisExpression','Super']:
        pass
    return copyExpression

# %%
def parse(contents, beautify):
    try:
        if beautify:
            contents = jsbeautifier.beautify(contents)
        if contents.strip()[0] == '<':
            contents = extractScriptFromHTML(contents)
        script = esprima.parseScript(contents, { 'range': True, 'loc': True })
        nodes = []
        for statement in script.body:
            operateStatement(statement, None, nodes)
        return (True, (contents, nodes))
    except Exception as e:
        return (False, e)

# %%
def parse_file(filename, beautify):
    try:
        with open(filename, encoding='cp437') as file:
            contents = file.read()
        return parse(contents, beautify)
    except Exception as e:
        return (False, e)

# %%
def parse_file_cached(filename, cachedfilename):
    try:
        with open(filename, encoding='cp437') as file:
            contents = file.read()
        if contents.strip()[0] == '<':
            contents = extractScriptFromHTML(contents)
        with open(cachedfilename, 'rb') as file:
            nodes = decoder.loads(file.read())
        return (True, (contents, nodes))
    except Exception as e:
        return (False, e)


