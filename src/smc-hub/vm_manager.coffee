
###########################
# Command line interface for VM manager
###########################
winston     = require('winston')
winston.remove(winston.transports.Console)
winston.add(winston.transports.Console, {level: 'debug', timestamp:true, colorize:true})

misc_node = require('smc-util-node/misc_node')
program   = require('commander')
daemon    = require('start-stop-daemon')

LOGS = join(process.env.HOME, 'logs')
program.usage('[start/stop/restart/status] [options]')
    .option('--pidfile [string]', 'store pid in this file', String, "#{LOGS}/vm_manager.pid")
    .option('--logfile [string]', 'write log to this file', String, "#{LOGS}/vm_manager.log")
    .option('-e')   # gets passed by coffee -e
    .parse(process.argv)

start_server = () ->
    require('./smc-hub/rethink').rethinkdb
        hosts : db_hosts
        pool  : 1
        cb    : (err, db) =>
            g = require('./smc-hub/smc_gcloud.coffee').gcloud(db:db)
            vms = g.vm_manager(opts)

main = () ->
    winston.debug("running as a deamon")
    # run as a server/daemon (otherwise, is being imported as a library)
    process.addListener "uncaughtException", (err) ->
        winston.debug("BUG ****************************************************************************")
        winston.debug("Uncaught exception: " + err)
        winston.debug(err.stack)
        winston.debug("BUG ****************************************************************************")

    async.series([
        (cb) ->
            misc_node.ensure_containing_directory_exists(program.pidfile, cb)
        (cb) ->
            misc_node.ensure_containing_directory_exists(program.logfile, cb)
        (cb) ->
            daemon({max:9999, pidFile:program.pidfile, outFile:program.logfile, errFile:program.logfile, logFile:'/dev/null'}, start_server)
    ])

if program._name.split('.')[0] == 'storage'
    main()